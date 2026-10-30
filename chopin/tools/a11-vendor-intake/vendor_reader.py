"""Bounded payload-backed read-only files; no filesystem implementation here."""
import ast
import bisect
import bz2
import collections
import concurrent.futures
import hashlib
import io
import lzma
import re
import stat
import struct
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

HELPER_SHA = "ab77c172463ba046173ff531c3cc90ea8df8cbb5f3280959d1ee02c0d84f0807"
MAX_NETWORK = 128 * 1024 * 1024
MAX_RANGE = 512 * 1024
MAX_PACKED_OPERATION = 16 * 1024 * 1024
MAX_RAW_OPERATION = 32 * 1024 * 1024
MAX_LOGICAL_READ = 16 * 1024 * 1024
MAX_LOGICAL_TOTAL = 64 * 1024 * 1024
MAX_MODULE = 16 * 1024 * 1024
MODULES = ("conninfra.ko", "met.ko", "connfem.ko", "bt_drv_6893.ko", "fmradio_drv_connac2x.ko",
           "fpsgo.ko", "gps_drv.ko", "sla.ko", "wlan_drv_gen4m.ko", "wmt_chrdev_wifi.ko")


def require(value, message):
    if not value:
        raise ValueError(message)


def reviewed_definitions(path):
    blob = Path(path).read_bytes()
    require(hashlib.sha256(blob).hexdigest() == HELPER_SHA, "Reviewed ROM helper hash differs")
    tree = ast.parse(blob)
    allowed = {"RemoteZip", "protobuf", "payload_boot"}
    nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
             or isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in allowed]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<reviewed ROM helper definitions>", "exec"), namespace)
    require(all(name in namespace for name in allowed), "Required reviewed definitions are missing")
    return namespace


def remote_class(base):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, request, response, code, message, headers):
            response.close()
            raise ValueError("HTTP redirects are rejected before reading their bodies")
        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    class BoundedRemoteZip(base):
        def __init__(self, url, opener=None):
            self.budget_lock = threading.Lock()
            self.reserved_bytes = 0
            self.body_received = 0
            self.range_requests = 0
            self.strong_etag = None
            self.opener = opener or urllib.request.build_opener(NoRedirect()).open
            super().__init__(url)
            require(0 < self.total <= 16 * 1024 ** 3, "Unexpected ROM size")
            self.body_received = 1

        def request(self, start, end):
            amount = end - start + 1
            require(0 <= start <= end and amount <= MAX_RANGE, "Invalid or oversized HTTP range")
            with self.budget_lock:
                # Include one byte used to detect an oversized body. Failed requests consume budget too.
                require(self.reserved_bytes + amount + 1 <= MAX_NETWORK, "Total response-byte budget reached")
                self.reserved_bytes += amount + 1
                self.range_requests += 1
            headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity",
                       "User-Agent": "chopin-bounded-vendor-intake/1"}
            if self.strong_etag:
                headers["If-Match"] = self.strong_etag
            response = self.opener(urllib.request.Request(self.url, headers=headers), timeout=35)
            try:
                require(response.status == 206, "Range refused; a full ROM download is prohibited")
                require(response.headers.get("Content-Encoding", "identity") == "identity", "Encoded HTTP ranges are rejected")
                content_range = response.headers.get("Content-Range", "")
                total = getattr(self, "total", None)
                if total is None:
                    require(re.fullmatch(r"bytes 0-0/[1-9][0-9]*", content_range), "Bad initial Content-Range")
                else:
                    require(content_range == f"bytes {start}-{end}/{total}", "Content-Range or ROM size changed")
                length = response.headers.get("Content-Length")
                require(length is None or length == str(amount), "Unexpected HTTP body length")
                tag = response.headers.get("ETag", "")
                if self.strong_etag:
                    require(tag == self.strong_etag, "ROM ETag changed or disappeared")
                elif tag and not tag.startswith("W/"):
                    with self.budget_lock:
                        if self.strong_etag:
                            require(tag == self.strong_etag, "Parallel ROM ETag mismatch")
                        self.strong_etag = tag
                return response
            except Exception:
                response.close()
                raise

        def read(self, count=-1):
            if count < 0:
                count = self.total - self.pos
            count = min(count, self.total - self.pos)
            require(0 <= count <= MAX_LOGICAL_READ, "Unbounded ZIP read is prohibited")
            result = []
            while count:
                offset = self.pos - self.cache_start
                if not 0 <= offset < len(self.cache):
                    amount = min(max(count, 64 * 1024), 2 * 1024 * 1024, self.total - self.pos)
                    chunks = [(start, min(MAX_RANGE, self.pos + amount - start))
                              for start in range(self.pos, self.pos + amount, MAX_RANGE)]

                    def fetch(item):
                        start, size = item
                        with self.request(start, start + size - 1) as response:
                            deadline = time.monotonic() + 45
                            body = []
                            received = 0
                            while received < size:
                                require(time.monotonic() < deadline, "HTTP range body deadline exceeded")
                                data = response.read1(min(256 * 1024, size - received))
                                require(data, "Truncated HTTP range body")
                                received += len(data)
                                with self.budget_lock:
                                    self.body_received += len(data)
                                body.append(data)
                            extra = response.read(1)
                            with self.budget_lock:
                                self.body_received += len(extra)
                            require(not extra, "Oversized HTTP range body")
                            return b"".join(body)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        self.cache = b"".join(pool.map(fetch, chunks))
                    self.cache_start = self.pos
                    self.downloaded = self.body_received
                    offset = 0
                amount = min(count, len(self.cache) - offset)
                result.append(self.cache[offset:offset + amount])
                self.pos += amount
                count -= amount
            return b"".join(result)
    return BoundedRemoteZip


def one(message, field, default=None):
    values = message.get(field, [] if default is None else [default])
    require(len(values) == 1, f"Missing or repeated protobuf field {field}")
    return values[0]


class PayloadPartition(io.RawIOBase):
    def __init__(self, remote, info, protobuf, prior_boot_sha):
        self.remote, self.protobuf = remote, protobuf
        self.pos = self.logical_bytes = self.read_calls = 0
        self.cache = collections.OrderedDict()
        self.cache_bytes = 0
        self.proof = {}
        require(info.compress_type == zipfile.ZIP_STORED and info.compress_size == info.file_size and not info.flag_bits & 1,
                "Payload must be an unencrypted stored ZIP member")
        remote.seek(info.header_offset)
        local = remote.read(30)
        require(local[:4] == b"PK\x03\x04", "Bad local ZIP header")
        name_bytes, extra = struct.unpack_from("<HH", local, 26)
        require(name_bytes <= 1024 and extra <= 65535, "Oversized local ZIP header")
        require(remote.read(name_bytes) == b"payload.bin", "Unexpected local ZIP member name")
        offset = info.header_offset + 30 + name_bytes + extra
        self.payload_end = offset + info.file_size
        require(self.payload_end <= remote.total, "Payload member exceeds ROM")
        remote.seek(offset)
        header = remote.read(24)
        magic, version, manifest_size, signature_size = struct.unpack(">4sQQI", header)
        require(magic == b"CrAU" and version == 2, "Unsupported payload header")
        require(0 < manifest_size <= 16 * 1024 * 1024 and signature_size <= 4 * 1024 * 1024,
                "Oversized payload manifest or metadata signature")
        manifest_raw = remote.read(manifest_size)
        manifest = protobuf(manifest_raw)
        self.block = one(manifest, 3, 4096)
        require(self.block == 4096, "Unexpected payload block size")
        self.data_begin = offset + 24 + manifest_size + signature_size
        require(self.data_begin <= self.payload_end, "Payload data start exceeds member")
        parts = [protobuf(blob) for blob in manifest.get(13, [])]
        boot = [part for part in parts if part.get(1) == [b"boot"]]
        require(len(boot) == 1, "A unique prior boot descriptor is required")
        boot_info = protobuf(one(boot[0], 7))
        require(one(boot_info, 1) == 134217728 and one(boot_info, 2).hex() == prior_boot_sha,
                "Manifest boot descriptor differs from the prior verified A11 boot")
        vendor = [part for part in parts if part.get(1) == [b"vendor"]]
        require(len(vendor) == 1, "A unique vendor partition is required")
        partition = vendor[0]
        new = protobuf(one(partition, 7))
        self.size = one(new, 1)
        self.expected_sha = one(new, 2)
        require(0 < self.size <= 4 * 1024 ** 3 and len(self.expected_sha) == 32,
                "Invalid vendor partition size or descriptor hash")
        blobs = partition.get(8, [])
        require(0 < len(blobs) <= 20000, "Unexpected vendor operation count")
        self.operations, self.intervals = [], []
        for index, blob in enumerate(blobs):
            operation = protobuf(blob)
            kind = one(operation, 1)
            require(kind in (0, 1, 6, 8) and not operation.get(4),
                    "Source/delta/discard operation is unsupported; no base image is assumed")
            extents = [protobuf(raw) for raw in operation.get(6, [])]
            require(extents, "Missing destination extents")
            length = 0
            for extent in extents:
                start, count = one(extent, 1), one(extent, 2)
                begin, end = start * self.block, (start + count) * self.block
                require(count > 0 and 0 <= begin < end <= self.size, "Invalid destination extent")
                self.intervals.append((begin, end, index, length))
                require(len(self.intervals) <= 100000, "Destination extent limit reached")
                length += count * self.block
            require(0 < length <= MAX_RAW_OPERATION, "Decompressed operation limit exceeded")
            if operation.get(7):
                require(one(operation, 7) == length, "Destination length differs from extent size")
            if kind == 6:
                require(one(operation, 3, 0) == 0, "ZERO operation unexpectedly carries data")
                packed_offset = packed_size = 0
                digest = None
            else:
                packed_offset, packed_size = one(operation, 2, 0), one(operation, 3)
                digest = one(operation, 8)
                require(len(digest) == 32 and 0 < packed_size <= MAX_PACKED_OPERATION,
                        "Operation is missing a valid compressed-data SHA or exceeds the size limit")
                require(0 <= packed_offset and self.data_begin + packed_offset + packed_size <= self.payload_end,
                        "Operation data exceeds payload")
            self.operations.append((kind, packed_offset, packed_size, length, digest))
        self.intervals.sort()
        for previous, current in zip(self.intervals, self.intervals[1:]):
            require(previous[1] <= current[0], "Overlapping destination extents")
        self.starts = [item[0] for item in self.intervals]
        self.manifest_sha = hashlib.sha256(manifest_raw).hexdigest()

    def seekable(self): return True
    def readable(self): return True
    def writable(self): return False
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        target = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset if whence == 2 else -1
        require(0 <= target <= self.size, "Partition seek outside bounds")
        self.pos = target
        return target

    def operation(self, index):
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        kind, offset, packed_size, length, digest = self.operations[index]
        if kind == 6:
            raw = bytes(length)
        else:
            self.remote.seek(self.data_begin + offset)
            packed = self.remote.read(packed_size)
            actual_sha = hashlib.sha256(packed).digest()
            require(len(packed) == packed_size and actual_sha == digest, "Payload operation SHA256 mismatch")
            if kind == 0:
                raw = packed
            else:
                decoder = bz2.BZ2Decompressor() if kind == 1 else lzma.LZMADecompressor(memlimit=64 * 1024 * 1024)
                raw = decoder.decompress(packed, max_length=length + 1)
                require(decoder.eof and not decoder.unused_data, "Incomplete or concatenated compressed operation")
            require(len(raw) == length, "Operation output length differs; implicit zero padding is prohibited")
        self.proof[index] = {"index": index, "type": kind, "compressed_bytes": packed_size,
            "raw_bytes": length, "compressed_data_sha256": digest.hex() if digest else None,
            "compressed_sha_verified": kind != 6, "zero_operation_explicit": kind == 6,
            "decoded_sha256": hashlib.sha256(raw).hexdigest()}
        while self.cache and self.cache_bytes + len(raw) > 64 * 1024 * 1024:
            _, old = self.cache.popitem(last=False)
            self.cache_bytes -= len(old)
        self.cache[index] = raw
        self.cache_bytes += len(raw)
        return raw

    def read(self, count=-1):
        require(0 <= count <= MAX_LOGICAL_READ, "Unbounded partition reads are prohibited")
        count = min(count, self.size - self.pos)
        self.read_calls += 1
        self.logical_bytes += count
        require(self.read_calls <= 20000 and self.logical_bytes <= MAX_LOGICAL_TOTAL,
                "Filesystem logical read budget reached")
        result = []
        while count:
            index = bisect.bisect_right(self.starts, self.pos) - 1
            require(index >= 0, "Requested block is absent from the full payload")
            begin, end, operation, relative = self.intervals[index]
            require(begin <= self.pos < end, "Requested block is not covered; no zero/base-data guess is allowed")
            amount = min(count, end - self.pos)
            raw = self.operation(operation)
            offset = relative + self.pos - begin
            result.append(raw[offset:offset + amount])
            self.pos += amount
            count -= amount
        return b"".join(result)

    def readinto(self, target):
        data = self.read(len(target))
        target[:len(data)] = data
        return len(data)


def parse_module(name, data):
    # Adapted from the reviewed diagnose_a12_modules.py parse function (SHA59f5e040...).
    # Keep its ARM64 / 64-byte __versions / absolute __crc_ format, adding bounds checks.
    require(name in MODULES and 64 <= len(data) <= MAX_MODULE, "Module is outside the fixed intake scope")
    require(data[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<HH", data, 16) == (1, 183),
            "Expected little-endian ARM64 relocatable ELF")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    entry_size, count, string_index = struct.unpack_from("<HHH", data, 58)
    require(entry_size == 64 and 0 < count <= 4096 and string_index < count and shoff >= 64
            and shoff + count * 64 <= len(data), "Invalid ELF section table")
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * 64) for index in range(count)]
    for header in headers:
        require(header[1] == 8 or header[4] + header[5] <= len(data), "ELF section exceeds module")
    names_header = headers[string_index]
    require(names_header[1] == 3, "Missing ELF section-name string table")
    names = data[names_header[4]:names_header[4] + names_header[5]]
    sections = {}
    for header in headers[1:]:
        require(header[0] < len(names) and b"\0" in names[header[0]:], "Invalid ELF section name")
        section_name = names[header[0]:].split(b"\0", 1)[0].decode("ascii")
        require(section_name not in sections, "Duplicate ELF section name")
        sections[section_name] = header
    require("__versions" in sections and ".modinfo" in sections, "Module is missing versions or modinfo")
    version_header, modinfo_header = sections["__versions"], sections[".modinfo"]
    require(version_header[1] == 1 and version_header[9] in (0, 64) and
            0 < version_header[5] <= 1024 * 1024 and version_header[5] % 64 == 0,
            "Invalid __versions record layout")
    require(modinfo_header[1] == 1 and modinfo_header[5] <= 65536, "Invalid .modinfo section")
    raw = data[version_header[4]:version_header[4] + version_header[5]]
    imports = {}
    for position in range(0, len(raw), 64):
        crc = struct.unpack_from("<Q", raw, position)[0]
        field = raw[position + 8:position + 64]
        require(b"\0" in field, "Unterminated module version symbol")
        symbol = field.split(b"\0", 1)[0].decode("ascii")
        require(crc <= 0xffffffff and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", symbol)
                and symbol not in imports, "Invalid or duplicate module import CRC")
        imports[symbol] = f"{crc:08x}"
    exports = {}
    for header in headers:
        if header[1] != 2:
            continue
        require(header[6] < count and header[9] == 24 and header[5] % 24 == 0, "Invalid ELF symbol table")
        strings_header = headers[header[6]]
        require(strings_header[1] == 3, "Invalid symbol string table link")
        strings = data[strings_header[4]:strings_header[4] + strings_header[5]]
        for position in range(header[4], header[4] + header[5], 24):
            number, _, _, section_index, value, _ = struct.unpack_from("<IBBHQQ", data, position)
            require(number < len(strings) and b"\0" in strings[number:], "Invalid ELF symbol name")
            symbol = strings[number:].split(b"\0", 1)[0].decode("ascii")
            if symbol.startswith("__crc_") and section_index == 0xfff1:
                require(value <= 0xffffffff and symbol[6:] not in exports, "Invalid duplicate peer export CRC")
                exports[symbol[6:]] = f"{value:08x}"
    info = data[modinfo_header[4]:modinfo_header[4] + modinfo_header[5]].split(b"\0")
    vermagic = [item[len(b"vermagic="):].decode("ascii") for item in info if item.startswith(b"vermagic=")]
    require(len(vermagic) == 1 and "modversions" in vermagic[0].split(), "A unique modversions vermagic is required")
    return {"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "vermagic": vermagic[0], "imports": dict(sorted(imports.items())), "peer_exports": dict(sorted(exports.items()))}


def module_manifests(partition, selected, on_module=None):
    from dissect.extfs.extfs import ExtFS
    require(selected and len(set(selected)) == len(selected) and all(name in MODULES for name in selected),
            "Module paths must come from the fixed allowlist")
    fs = ExtFS(partition)
    require(fs.block_size in (1024, 2048, 4096) and fs.block_count * fs.block_size <= partition.size,
            "Unsupported or oversized ext4 geometry")
    require(fs.sb.s_feature_incompat & 0x40 and fs.sb.s_state & 1 and not fs.sb.s_feature_incompat & 4,
            "Only clean ext4 images are read; journal replay is prohibited")

    def child(parent, name):
        require(parent.filetype == stat.S_IFDIR and 0 <= parent.size <= 2 * 1024 * 1024,
                "Unexpected directory or symlink in the fixed module path")
        for index, node in enumerate(parent.iterdir()):
            require(index < 4096, "Directory entry limit reached")
            if node.filename == name:
                return node
        raise ValueError("Requested module path is missing: " + name)

    directory = child(child(fs.root, "lib"), "modules")
    rows, total = [], 0
    for name in selected:
        node = child(directory, name)
        require(node.filetype == stat.S_IFREG and not node.inode.i_flags & 0x804,
                "Module must be a plain regular, unencrypted, uncompressed file")
        require(0 < node.size <= MAX_MODULE, "Module file size exceeds limit")
        total += node.size
        require(total <= 32 * 1024 * 1024, "Total selected module-byte budget reached")
        data = node.open().read(node.size + 1)
        require(len(data) == node.size, "Truncated module file")
        rows.append(parse_module(name, data))
        if on_module is not None:
            on_module(rows[-1])
    return rows, {"filesystem": "ext4", "block_size": fs.block_size, "blocks": fs.block_count,
        "state": fs.sb.s_state, "feature_incompat": fs.sb.s_feature_incompat,
        "journal_replayed": False, "filesystem_checksums_independently_verified": False}

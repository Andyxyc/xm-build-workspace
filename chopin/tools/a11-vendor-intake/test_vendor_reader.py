"""Synthetic payload/ELF tests. No firmware, network or device is accessed."""
import bz2
import hashlib
import io
import json
import lzma
import re
import struct
import unittest
import zipfile
from pathlib import Path
from vendor_reader import MAX_NETWORK, PayloadPartition, parse_module, remote_class, reviewed_definitions

HELPER = None
PRIOR_BOOT = "a0fbb496a41d93d171f6fbd72c09023174c98dd396e215dc6af5f3a05089711c"


def integer(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def message(fields):
    return b"".join(integer((number << 3) | (2 if isinstance(value, bytes) else 0)) +
                    (integer(len(value)) + value if isinstance(value, bytes) else integer(value))
                    for number, value in fields)


def module_bytes(crc=0x2d3d4373, symbol=b"module_layout", vermagic=b"4.14.186-fixture SMP preempt mod_unload modversions aarch64"):
    # Same ELF64 and 64-byte record shape as abi_selector/host-test.py; all bytes are generated.
    versions = struct.pack("<Q", crc) + symbol + b"\0" + bytes(55 - len(symbol))
    names = b"\0.shstrtab\0__versions\0.modinfo\0"
    info = b"vermagic=" + vermagic + b"\0"
    positions = (64, 64 + len(versions), 64 + len(versions) + len(names))
    shoff = (positions[2] + len(info) + 7) // 8 * 8
    out = bytearray(shoff + 4 * 64)
    struct.pack_into("<16sHHIQQQIHHHHHH", out, 0, b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8),
                     1, 183, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 4, 1)
    for position, data in zip(positions, (versions, names, info)):
        out[position:position + len(data)] = data
    for index, label, kind, offset, size in (
        (1, b".shstrtab", 3, positions[1], len(names)),
        (2, b"__versions", 1, positions[0], len(versions)),
        (3, b".modinfo", 1, positions[2], len(info)),
    ):
        struct.pack_into("<IIQQQQIIQQ", out, shoff + index * 64,
                         names.index(label + b"\0"), kind, 0, 0, offset, size, 0, 0, 1, 0)
    return bytes(out)


def payload_zip(rows, size, corrupt_hash=False, boot_hash=PRIOR_BOOT):
    operations, data = [], bytearray()
    for index, (kind, raw, extents) in enumerate(rows):
        packed = raw if kind == 0 else bz2.compress(raw) if kind == 1 else lzma.compress(raw) if kind == 8 else b""
        fields = [(1, kind), (2, len(data)), (3, len(packed))]
        for start, count in extents:
            fields.append((6, message([(1, start), (2, count)])))
        fields.append((7, sum(count for _, count in extents) * 4096))
        if kind != 6:
            digest = hashlib.sha256(packed).digest()
            fields.append((8, bytes(32) if corrupt_hash and index == 0 else digest))
        operations.append(message(fields))
        data.extend(packed)
    boot = message([(1, b"boot"), (7, message([(1, 134217728), (2, bytes.fromhex(boot_hash))]))])
    vendor = message([(1, b"vendor"), (7, message([(1, size), (2, bytes(32))]))] + [(8, item) for item in operations])
    manifest = message([(3, 4096), (13, boot), (13, vendor)])
    payload = struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 0) + manifest + data
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("payload.bin", payload)
    return out.getvalue()


def partition_from(blob):
    handle = io.BytesIO(blob)
    handle.total = len(blob)
    with zipfile.ZipFile(handle) as archive:
        info = archive.getinfo("payload.bin")
        return PayloadPartition(handle, info, HELPER["protobuf"], PRIOR_BOOT)


class FakeResponse(io.BytesIO):
    status = 206
    def __init__(self, body, start, end, total, status=206, changed_range=False, extra=False):
        super().__init__(body + (b"!" if extra else b""))
        self.status = status
        self.headers = {"Content-Range": f"bytes {start}-{end}/{total + int(changed_range)}",
                        "Content-Length": str(end - start + 1), "ETag": '"fixture"'}


class FakeHTTP:
    def __init__(self, blob, **options):
        self.blob, self.options, self.calls = blob, options, []
    def __call__(self, request, timeout):
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", request.get_header("Range"))
        start, end = map(int, match.groups())
        self.calls.append((start, end))
        return FakeResponse(self.blob[start:end + 1], start, end, len(self.blob), **self.options)


class PayloadFixture(unittest.TestCase):
    def test_replace_bzip_xz_zero(self):
        rows = [(0, b"a" * 4096, [(0, 1)]), (1, b"b" * 4096, [(1, 1)]),
                (8, b"c" * 4096, [(2, 1)]), (6, bytes(4096), [(3, 1)])]
        reader = partition_from(payload_zip(rows, 16384))
        self.assertEqual(reader.read(16384), b"a"*4096 + b"b"*4096 + b"c"*4096 + bytes(4096))
        self.assertEqual(len(reader.proof), 4)
        self.assertEqual(sum(row["compressed_sha_verified"] for row in reader.proof.values()), 3)

    def test_bad_operation_sha(self):
        reader = partition_from(payload_zip([(8,b"x"*4096,[(0,1)])],4096,corrupt_hash=True))
        with self.assertRaisesRegex(ValueError,"SHA256"):reader.read(1)
        self.assertFalse(reader.proof)

    def test_exact_decompression_length(self):
        reader = partition_from(payload_zip([(1,b"x"*4000,[(0,1)])],4096))
        with self.assertRaisesRegex(ValueError,"length"):reader.read(1)

    def test_noncontiguous_extent_order(self):
        reader = partition_from(payload_zip([(0,b"a"*4096+b"b"*4096,[(2,1),(0,1)])],12288))
        self.assertEqual(reader.read(4096),b"b"*4096)
        reader.seek(8192)
        self.assertEqual(reader.read(4096),b"a"*4096)

    def test_uncovered_block_not_guessed(self):
        reader = partition_from(payload_zip([(6,bytes(4096),[(1,1)])],8192))
        with self.assertRaises(ValueError):reader.read(1)

    def test_overlapping_extents_rejected(self):
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            partition_from(payload_zip([(6,bytes(4096),[(0,1)]),(6,bytes(4096),[(0,1)])],4096))

    def test_delta_and_discard_rejected(self):
        for kind in (2,4,5,7,9):
            with self.assertRaises(ValueError):partition_from(payload_zip([(kind,b"x"*4096,[(0,1)])],4096))

    def test_prior_boot_binding(self):
        with self.assertRaisesRegex(ValueError,"prior verified"):
            partition_from(payload_zip([(6,bytes(4096),[(0,1)])],4096,boot_hash="00"*32))

    def test_unbounded_reads_and_seek_rejected(self):
        reader = partition_from(payload_zip([(6,bytes(4096),[(0,1)])],4096))
        for value in (-1,16*1024*1024+1):
            with self.assertRaises(ValueError):reader.read(value)
        with self.assertRaises(ValueError):reader.seek(-1)
        with self.assertRaises(ValueError):reader.seek(4097)

    def test_lazy_untouched_operation_not_fetched(self):
        reader = partition_from(payload_zip([(1,b"a"*4096,[(0,1)]),(8,b"b"*4096,[(1,1)])],8192))
        self.assertEqual(reader.read(10),b"a"*10)
        self.assertEqual(list(reader.proof),[0])

    def test_deflated_payload_rejected(self):
        original=payload_zip([(6,b"",[(0,1)])],4096)
        with zipfile.ZipFile(io.BytesIO(original))as archive:payload=archive.read("payload.bin")
        result=io.BytesIO()
        with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED)as archive:archive.writestr("payload.bin",payload)
        with self.assertRaisesRegex(ValueError,"stored"):partition_from(result.getvalue())

    def test_oversized_zero_operation_rejected_before_allocation(self):
        with self.assertRaisesRegex(ValueError,"operation limit"):
            partition_from(payload_zip([(6,b"",[(0,8193)])],8193*4096))

    def test_reader_cannot_write(self):
        original=payload_zip([(6,b"",[(0,1)])],4096)
        reader=partition_from(original)
        self.assertFalse(reader.writable())
        with self.assertRaises((io.UnsupportedOperation,NotImplementedError)):reader.write(b"change")
        self.assertEqual(reader.remote.getvalue(),original)


class RangeFixture(unittest.TestCase):
    def test_parallel_ranges_and_budget(self):
        body = bytes(range(256))*16384
        transport = FakeHTTP(body)
        reader = remote_class(HELPER["RemoteZip"])("https://fixture.invalid/rom.zip", transport)
        self.assertEqual(reader.read(2*1024*1024),body[:2*1024*1024])
        self.assertGreaterEqual(len(transport.calls),5)
        self.assertTrue(all(end-start+1<=512*1024 for start,end in transport.calls))
        reader.reserved_bytes=MAX_NETWORK
        reader.seek(3*1024*1024)
        with self.assertRaisesRegex(ValueError,"budget"):reader.read(1)

    def test_full_response_rejected(self):
        with self.assertRaisesRegex(ValueError,"Range refused"):
            remote_class(HELPER["RemoteZip"])("https://fixture.invalid/rom.zip",FakeHTTP(bytes(100),status=200))

    def test_changed_range_rejected(self):
        transport=FakeHTTP(bytes(100))
        reader=remote_class(HELPER["RemoteZip"])("https://fixture.invalid/rom.zip",transport)
        transport.options["changed_range"]=True
        with self.assertRaisesRegex(ValueError,"Content-Range"):reader.read(10)

    def test_oversized_range_body_rejected(self):
        transport=FakeHTTP(bytes(100))
        reader=remote_class(HELPER["RemoteZip"])("https://fixture.invalid/rom.zip",transport)
        transport.options["extra"]=True
        with self.assertRaisesRegex(ValueError,"Oversized"):reader.read(10)


class ElfFixture(unittest.TestCase):
    def test_real_generated_elf(self):
        parsed=parse_module("conninfra.ko",module_bytes())
        self.assertEqual(parsed["imports"],{"module_layout":"2d3d4373"})
        self.assertEqual(parsed["sha256"],hashlib.sha256(module_bytes()).hexdigest())

    def test_foreign_name_or_truncated_elf(self):
        for name,data in (("not-allowed.ko",module_bytes()),("met.ko",module_bytes()[:-1])):
            with self.assertRaises(ValueError):parse_module(name,data)

    def test_crc_overflow_or_non_modversions(self):
        for data in (module_bytes(crc=1<<40),module_bytes(vermagic=b"4.14 fixture SMP")):
            with self.assertRaises(ValueError):parse_module("met.ko",data)

    def test_A11_bt_basename_is_accepted_without_aliasing(self):
        data=module_bytes(crc=0x1234abcd)
        parsed=parse_module("bt_drv.ko",data)
        self.assertEqual(parsed["file"],"bt_drv.ko")
        self.assertEqual(parsed["imports"],{"module_layout":"1234abcd"})
        self.assertEqual(parsed["sha256"],hashlib.sha256(data).hexdigest())

    def test_A11_kheaders_basename_uses_the_same_ELF_parser(self):
        data=module_bytes(crc=0x2345bcde)
        parsed=parse_module("kheaders.ko",data)
        self.assertEqual(parsed["file"],"kheaders.ko")
        self.assertEqual(parsed["imports"],{"module_layout":"2345bcde"})
        self.assertEqual(parsed["sha256"],hashlib.sha256(data).hexdigest())

    def test_new_names_do_not_allow_paths_or_invented_aliases(self):
        for name in ("../bt_drv.ko","bt_drv.ko/../kheaders.ko","kheaders.ko.xz","bt_drv_a11.ko"):
            with self.assertRaises(ValueError):parse_module(name,module_bytes())


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--helper",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    HELPER=reviewed_definitions(args.helper)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
    report={"status":"PASS_SYNTHETIC_PAYLOAD_RANGE_ELF_CASES_ONLY"if result.wasSuccessful()else"FAIL_SYNTHETIC_CASES",
            "tests_run":result.testsRun,"ROM_accessed":False,"ext4_reader_executed":False,
            "source_sha256":{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                             for name in ("test_vendor_reader.py","vendor_reader.py")}}
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    raise SystemExit(not result.wasSuccessful())

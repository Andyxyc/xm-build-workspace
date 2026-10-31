"""Read bounded official Android11 boot bytes; report ABI evidence, never flash."""
import ast
import concurrent.futures
import gzip
import io
import hashlib
import json
import os
import re
import signal
import struct
import sys
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path
from arm64_export_crc import exported as absolute_exports
from vmlinux_to_elf.core.kallsyms import KallsymsFinder

OUT = Path('a11-rom-analysis')
OUT.mkdir(exist_ok=True)
IMAGE_SHA = '6702e417fc0f731923be2f35e55ba96ffe0644e1a67275d7e5ebd09e91a865f1'
SYMVERS_SHA = '4c4000b1ab19460eca9dabf7a9d5537a044fb6207b945e947ae75919ca8b8c63'
SOURCE = '16c713d934ab7cfed5c4798497c48bab7e9db025'
PARSER_SHA = 'ab77c172463ba046173ff531c3cc90ea8df8cbb5f3280959d1ee02c0d84f0807'
URL = ('https://bigota.d.miui.com/V12.5.7.0.RKPMIXM/'
       'miui_CHOPINGlobal_V12.5.7.0.RKPMIXM_c79b13bbdc_11.0.zip')
report = {'status': 'IN_PROGRESS', 'source_commit': os.environ.get('GITHUB_SHA'),
          'reference_kernel_source': SOURCE, 'reference_image_sha256': IMAGE_SHA,
          'firmware': 'V12.5.7.0.RKPMIXM Android11 chopin global', 'official_url': URL,
          'catalog_md5_reference_only': 'c79b13bbdc7f6ba5e21aa869e69c8278',
          'catalog_source': 'https://t.me/s/MIUIUpdatesTracker?after=15518',
          'full_ROM_downloaded': False, 'full_ROM_hash_verified': False,
          'flashed': False, 'hardware_tested': False, 'max_network_bytes': 96*1024*1024,
          'raw_firmware_uploaded': False}
remote = None


def save(stage):
    report['stage'] = stage
    if remote is not None:
        report['network_bytes'] = remote.downloaded
    (OUT/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'stage': stage, 'status': report['status'],
                      'network_bytes': report.get('network_bytes', 0)}), flush=True)


def deadline(signum, frame):
    raise TimeoutError('Bounded ABI probe expired at '+report.get('stage', 'unknown'))


def inspect_exports(image, expected, label):
    found = KallsymsFinder(image, 64)
    symbols = {symbol.name: symbol for symbol in found.symbols}
    report.setdefault('normalizer_diagnostics', {})[label] = {
        'is_relocated': found.is_relocated, 'symbols_recovered': len(symbols),
        'text_symbol_present': '_text' in symbols,
        'selected_symbol_names': [name for name in ['_text', '_stext', 'stext',
                                  'start_kernel', 'remap_pfn_range'] if name in symbols],
        'kernel_text_candidate': hex(found.kernel_text_candidate)
                                  if found.kernel_text_candidate is not None else None,
        'first_symbol_names': [symbol.name for symbol in found.symbols[:12]]}
    save(report['stage'])
    # The Android11 image has no _text in the parsed table. Derive one unique
    # base from relocated export-name pointers, then independently locate CRCs.
    return absolute_exports(found.kernel_img, expected)



def embedded_config_values(image):
    """Bounded gzip IKCONFIG from the exact firmware Image, not kheaders cache."""
    marker = b'IKCFG_ST'
    positions = [m.start() for m in re.finditer(re.escape(marker), image)]
    assert len(positions) == 1, 'Expected one IKCONFIG frame'
    dec = zlib.decompressobj(31)
    raw = dec.decompress(image[positions[0]+len(marker):], 1024*1024+1)
    assert len(raw) <= 1024*1024 and dec.eof and not dec.unconsumed_tail
    assert dec.unused_data.startswith(b'IKCFG_ED'), 'IKCONFIG end marker missing'
    values = {}
    for line in raw.decode('ascii').splitlines():
        if line.startswith('# CONFIG_') and line.endswith(' is not set'):
            name, value = line[2:-11], 'n'
        elif re.fullmatch(r'CONFIG_[A-Za-z0-9_]+=[^\r\n]{1,1024}', line):
            name, value = line.split('=', 1)
        else:
            continue
        assert name not in values, 'Duplicate config key'
        values[name] = value
    assert 1000 <= len(values) <= 20000
    return {'config_sha256': hashlib.sha256(raw).hexdigest(),
            'config_bytes': len(raw), 'key_values': values,
            'source': 'IKCONFIG inside SHA-pinned official stock Image',
            'compiled_object_consistency_claim': False}

try:
    save('verify_exact_reference_and_parser')
    reference = Path('a11-reference')
    assert (reference/'build-logs/root-build-complete.txt').read_text(encoding='utf-8').strip() == SOURCE
    image = (reference/'kernel_workspace/android-kernel/out/arch/arm64/boot/Image').read_bytes()
    assert hashlib.sha256(image).hexdigest() == IMAGE_SHA
    symvers = (reference/'release-evidence/ported.Module.symvers').read_bytes()
    assert hashlib.sha256(symvers).hexdigest() == SYMVERS_SHA
    expected = {q[1]: int(q[0], 16) for line in symvers.decode().splitlines()
                if len(q := line.split()) >= 3 and q[2] == 'vmlinux'}
    assert len(expected) > 10000
    helper = Path('chopin/tools/rom_abi_probe.py').read_bytes()
    assert hashlib.sha256(helper).hexdigest() == PARSER_SHA
    # Reuse only the reviewed definitions, not the older workflow's executable main.
    tree = ast.parse(helper)
    definitions = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom,
                                                         ast.FunctionDef, ast.ClassDef))]
    namespace = {}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<pinned ABI definitions>', 'exec'), namespace)
    class ParallelRemoteZip(namespace['RemoteZip']):
        """Same byte/header limits; four bounded ranges per prefetch, no full fetch."""
        def read(self, n=-1):
            if n < 0:
                n = self.total-self.pos
            n = min(n, self.total-self.pos)
            assert 0 <= n <= 96*1024*1024
            result = []
            while n:
                offset = self.pos-self.cache_start
                if not 0 <= offset < len(self.cache):
                    amount = min(max(n, 64*1024), 2*1024*1024, self.total-self.pos)
                    assert self.downloaded+amount <= 96*1024*1024
                    chunks = [(start, min(512*1024, self.pos+amount-start))
                              for start in range(self.pos, self.pos+amount, 512*1024)]
                    def fetch(item):
                        start, size = item
                        with self.request(start, start+size-1) as response:
                            assert response.headers.get('Content-Range') == f'bytes {start}-{start+size-1}/{self.total}'
                            body = response.read(size+1)
                            assert len(body) == size, 'Truncated or oversized Range body'
                            return body
                    # Reserve requested bytes before submitting; failures cannot permit an unlimited retry.
                    self.downloaded += amount
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        data = b''.join(pool.map(fetch, chunks))
                    self.cache_start, self.cache = self.pos, data
                    offset = 0
                    print(json.dumps({'range_start': self.pos, 'range_bytes': amount,
                                      'downloaded_bytes': self.downloaded}), flush=True)
                amount = min(n, len(self.cache)-offset)
                result.append(self.cache[offset:offset+amount])
                self.pos += amount
                n -= amount
            return b''.join(result)
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(900)
    save('reference_parser_selfcheck')
    selfcheck = inspect_exports(image, expected, 'reference')
    assert not selfcheck['different_export_crcs'] and not selfcheck['candidate_exports_missing_from_firmware']
    report['reference_parser_selfcheck'] = selfcheck
    del image
    save('open_official_remote_zip')
    remote = ParallelRemoteZip(URL)
    report['parallel_range_workers'] = 4
    report['max_single_range_bytes'] = 512*1024
    report['ROM_total_bytes'] = remote.total
    with zipfile.ZipFile(remote) as archive:
        names = archive.namelist()
        matches = [n for n in names if n == 'boot.img' or n.endswith('/boot.img')]
        report['boot_container_entries'] = [n for n in names if n in matches or n == 'payload.bin']
        save('read_boot_member_only')
        if len(matches) == 1:
            info = archive.getinfo(matches[0])
            assert info.file_size == 134217728 and info.compress_size < 96*1024*1024
            boot = archive.read(info)
            report['boot_zip_member_crc_verified'] = True
        else:
            assert not matches and names.count('payload.bin') == 1
            boot, proof = namespace['payload_boot'](remote, archive.getinfo('payload.bin'))
            report.update(proof)
    assert len(boot) == 134217728 and boot[:8] == b'ANDROID!'
    size = struct.unpack_from('<I', boot, 8)[0]
    page = struct.unpack_from('<I', boot, 36)[0]
    assert page in (2048, 4096) and 0 < size < 96*1024*1024 and page+size <= len(boot)
    report['boot_sha256'] = hashlib.sha256(boot).hexdigest()
    report['boot_os_version_field'] = struct.unpack_from('<I', boot, 44)[0]
    image = gzip.GzipFile(fileobj=io.BytesIO(boot[page:page+size])).read(96*1024*1024+1)
    assert 0 < len(image) <= 96*1024*1024 and image[56:60] == b'ARMd'
    report['image_sha256'] = hashlib.sha256(image).hexdigest()
    assert report['boot_sha256'] == 'a0fbb496a41d93d171f6fbd72c09023174c98dd396e215dc6af5f3a05089711c'
    assert report['image_sha256'] == '35cc28163c6e0c766418d06f60c22840de2f1b9d8a1b79afc398cb37182d015f'
    config = embedded_config_values(image)
    (OUT/'stock-embedded-config-values.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    report['embedded_config'] = {k: v for k, v in config.items() if k != 'key_values'}
    report['embedded_config']['keys'] = len(config['key_values'])
    banner = re.search(rb'Linux version [^\x00\n]{1,400}', image)
    assert banner
    report['kernel_banner'] = banner[0].decode(errors='replace')
    save('recover_firmware_export_tables')
    report['export_comparison'] = inspect_exports(image, expected, 'firmware')
    report['status'] = 'PASS_BOUNDED_EXTRACTION_AND_CRC_COMPARISON_ONLY'
    report['compatibility_claim'] = False
    report['limitations'] = [
        'ZIP CRC or payload SHA validates the extracted member, not the entire ROM provenance/hash.',
        'CRC agreement is static ABI evidence; differences identify work, not a device failure.',
        'No Android11 vendor module import set, physical boot, Wi-Fi, recovery decryption or power acceptance here.']
    save('complete')
except Exception as error:
    report['status'] = 'FAIL_OR_EXTERNAL_SOURCE_BLOCKED_NO_COMPATIBILITY_CLAIM'
    report['error'] = type(error).__name__+': '+str(error)
    save(report.get('stage', 'unknown'))
    raise
finally:
    signal.alarm(0)

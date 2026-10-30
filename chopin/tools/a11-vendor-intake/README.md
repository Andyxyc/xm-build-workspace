# Bounded A11 vendor module intake

## Optional directory inventory

Add --inventory to the existing intake command to save metadata for the same
fixed /lib/modules directory before selected module files are opened. The
default command and module allowlist are unchanged. This is not a recursive
filesystem search.

Each entry records only name, size and type. The existing 4096-entry and
2 MiB directory limits remain, with the same payload-operation SHA and
network/read budgets. Member files and symlink targets are not opened for
the inventory. Whole payload operations still have to be fetched and checked
when their blocks contain requested metadata; this does not claim that an
operation contains no adjacent file bytes.

An optional on_inventory callback receives the snapshot before the selected
file loop. The CLI writes it to directory_inventory immediately, so a later
missing selected file still returns BLOCKED/exit 2 with that snapshot retained.
Invalid entries, parser warnings or an exceeded limit retain an incomplete
snapshot and fail. An incomplete snapshot must not be treated as a complete
module list. Normal directory enumeration is not independent ext4 checksum
verification.

Completed official reads covered wlan_drv_gen4m.ko, conninfra.ko, met.ko and
wmt_chrdev_wifi.ko. The complete parsed R directory contains nine regular
.ko files, so those four files do not establish the entire R module family.
The remaining observed files are bt_drv.ko (343880 bytes), fpsgo.ko (40496),
gps_drv.ko (408456), kheaders.ko (3275112) and sla.ko (36552).

This v3 proposal only adds the actual bt_drv.ko and kheaders.ko basenames to
the read allowlist. It does not map bt_drv.ko to bt_drv_6893.ko or invent an
alias. The other three names were already allowed. The next explicit batch
is --module bt_drv.ko --module fpsgo.ko --module gps_drv.ko --module kheaders.ko
--module sla.ko --inventory. All five together total 4104496 bytes, within
the unchanged selected-file budget. Keep kheaders content analysis in the
same reviewed read batch rather than fetching that file twice.

The input inventory is tied to payload manifest SHA-256
8aa942f0442c9509943ddf3e1fd0e27a26a897ff3f41f122a5a1b6a39b24c4c5.
That is evidence for this fixed official A11 probe only. It does not add an
AK3 firmware/hash binding, rename a payload or change universal installer
selection. Transport, manifest parsing, operation SHA verification, ELF
parsing, limits and failure handling stay unchanged. A missing file still
fails; four prior module reads and this source proposal are not an R kernel
build, device test or compatibility acceptance.

The new test_inventory.py covers metadata-only traversal, limits, partial
failure preservation and the unchanged default selected-file path using fake
inodes. The extended cloud ext4 fixture also checks a real CLI failure with
synthetic HTTP: connfem.ko is deliberately absent, so the command must return
exit 2/BLOCKED while keeping its complete directory inventory. No live ROM
URL is opened by that fixture. The v2 cloud run passed those generated-ext4
cases and the actual directory inventory; this v3 batch has not run.

This tool reads selected module files from the fixed official chopin
V12.5.7.0.RKPMIXM OTA. It never downloads a full ROM/vendor image, mounts a
filesystem, loads a module or accesses a phone. Only derived module hashes,
vermagic, import CRCs, peer export CRCs and read proofs are written.

The previously verified A11 boot descriptor hash is pinned. The current
manifest must contain that same boot hash and 128 MiB size, but the boot is
not downloaded again. This connects the intake to the earlier boot evidence;
it is not a fresh boot-byte verification or OEM-signature authentication.

The pinned rom_abi_probe.py definitions are loaded by AST, without executing
its historical main. Its RemoteZip/protobuf/payload_boot definitions have
SHA-256 ab77c172463ba046173ff531c3cc90ea8df8cbb5f3280959d1ee02c0d84f0807.
The four-worker range strategy follows a11_rom_abi.py. Each request is at
most 512 KiB; redirects, HTTP 200, changed ranges, encoded bodies, extra data
and a changing strong ETag are rejected. Failed requests consume the budget.
The reported body-byte limit excludes HTTP/TLS header overhead.

The vendor partition is a read-only virtual file. Destination extents map
each filesystem read to its payload operation. The entire accessed operation
is fetched, its data SHA-256 is checked, and only then is REPLACE/BZ2/XZ
decoded. Output length must exactly match destination extents. Explicit ZERO
operations supply zeros; an uncovered block never gets guessed zeros or old
partition data. Delta/source-copy/discard operations are rejected. Decoded
operations use a bounded memory cache, not a vendor-sized temporary image.

Filesystem parsing uses the existing
[Dissect extfs reader at its fixed 3.15 source](https://github.com/fox-it/dissect.extfs/blob/b6d907c2019373bb79f1c96850cabd1a1c123ea0/dissect/extfs/extfs.py).
There is no new ext4 implementation here. Only a clean ext4 image is read;
the journal is never replayed. Directory and file reads are bounded, and
symlinks, encryption and compression on the selected module file are
rejected. Separate ext4 checksum verification is not claimed.

The dependency lock selects these three exact pure Python wheels by URL
and SHA-256. No native extension, Rust build or local environment install is
needed. Small version-specific PyPI metadata is retained separately.

| Dependency | Version | Wheel SHA-256 | License metadata |
| --- | --- | --- | --- |
| dissect.extfs | 3.15 | 9c67e64552eedc58ecbbdda82287a6c8fbf8b29d99a7b55073d838233d6dfcab | AGPL-3.0-or-later |
| dissect.cstruct | 4.7 | 0427621ce67baa3106df2dc63a320d0a7f5c2da88ba3faf2ef5886a1a6b458fd | Apache-2.0 |
| dissect.util | 3.24 | 031f91d7523818a3aced4d17594996bcc39bc4d93ffacc0b15a7b718c9b437cb | Apache-2.0 |

Sources: [extfs release](https://pypi.org/project/dissect.extfs/3.15/),
[cstruct release](https://pypi.org/project/dissect.cstruct/4.7/),
[util release](https://pypi.org/project/dissect.util/3.24/).
Keep those packages' license files and attribution; they are external
dependencies rather than source copied into the kernel.

The ELF parser adapts the prior pure parse function from
diagnose_a12_modules.py (SHA-256
59f5e040aa233f6b2568b2c2f521a3d972bb2c6ed8ef709c4feaea0ac99cd36c).
It retains ARM64 little-endian relocatable ELF, 64-byte __versions records,
32-bit CRC values and absolute __crc_ peer exports, with bounds checks.
Missing/duplicate/unsupported section layouts fail without patching CRCs.

| Bound | Maximum |
| --- | --- |
| Reserved HTTP body bytes for the ROM | 128 MiB, including one oversize-detection byte per request |
| One HTTP range | 512 KiB, four workers |
| Compressed / decoded operation | 16 / 32 MiB |
| Decoded-operation cache | 64 MiB |
| Total filesystem logical reads | 64 MiB and 20,000 reads |
| One module / selected modules combined | 16 / 32 MiB |
| Process address space | 768 MiB |
| Main alarm / outer cloud-job timeout | 900 seconds / 20 minutes |

The alarm can wait for outstanding bounded HTTP workers to close; the outer
job timeout is the final wall limit. Network timeouts, budget exhaustion,
unsupported features and missing selected files are recorded as blocked.
Completed module manifests survive a later selected-file failure, with the
remaining names and incomplete status explicit. There is no automatic
unbounded retry, larger budget or full-image fallback.

Copy the source mapping in prepared-state.json after review. In a disposable
Linux cloud job, install only the locked wheels:

```text
python3 -m pip install --no-deps --no-compile --require-hashes -r chopin/tools/a11-vendor-intake/requirements.lock
python3 -B chopin/tools/a11-vendor-intake/test_vendor_reader.py --helper chopin/tools/rom_abi_probe.py --report UNIT_REPORT_JSON
python3 -B chopin/tools/a11-vendor-intake/ext4_fixture.py --helper chopin/tools/rom_abi_probe.py --report EXT4_REPORT_JSON
python3 -B chopin/tools/a11-vendor-intake/intake.py --helper chopin/tools/rom_abi_probe.py --out NEW_DERIVED_OUTPUT_DIRECTORY --module bt_drv.ko --module fpsgo.ko --module gps_drv.ko --module kheaders.ko --module sla.ko --inventory
```

Default intake still selects only conninfra.ko and met.ko. --module accepts
only names from the reviewed tool allowlist. --all-modules includes historical
names that are absent from this R inventory, so it is not the remaining-file
command. Use the explicit five-name batch above.
Files are read only from /lib/modules in the vendor filesystem. A missing
name does not trigger a whole-filesystem search or silently change scope.

The reviewed workflows have run fixed official batches after synthetic cases
on scoped pushes. This proposal does not change or start a workflow. The
next five-name command must be merged with the separate kheaders analysis
before a single cloud read. Upload paths remain derived JSON only.

The real-ext4 fixture uses the cloud runner's existing mke2fs on a new 32 MiB
ordinary temporary file populated with generated ELF fixtures. It wraps that
file in a synthetic OTA and verifies selected-file hashes, untouched
operations and symlink rejection. It never mounts the image, formats a disk,
uses OEM content or uploads raw fixtures. This fixture has not run locally.

An operation SHA proves bytes relative to the manifest. The complete ROM
hash, payload ZIP CRC, full vendor hash and OEM payload signature are not
verified by a partial read. New import records are evidence for a fourth ABI
family, not proof that any kernel, Android11 ROM or physical driver works.

The prior three-module intake and subsequent wmt_chrdev_wifi.ko plus inventory
results remain separate evidence. This v3 preparation does not reread those
files or claim that the remaining five imports or embedded headers passed.

Root integration: after the reader, inventory, ext4 and generated-header fixtures pass, scoped push reads only bt_drv.ko, fpsgo.ko, gps_drv.ko, sla.ko and kheaders.ko. The prior four actual module records stay separate and are reused. kheaders is limited to 4MiB and only selected generated-header hashes/macros are emitted; cache freshness is not certified. A failed analyzer retains module import evidence and fails the job. No phone commands or AK3 changes.

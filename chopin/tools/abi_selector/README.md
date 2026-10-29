# Chopin vendor ABI selector

The selector reads ELF64 little-endian AArch64 modules and their actual
64-byte `__versions` records. It does not choose by Android release, ROM
name, serial number, UID, build fingerprint or a whole-firmware hash.

| Profile | cpu_hwcaps | cpu_hwcap_keys | remap_pfn_range | find_vma |
| --- | --- | --- | --- | --- |
| legacy | be9f1a32 | 77af701b | f79cd398 | 30e3495c |
| early | f2352f28 | 37c71621 | f79cd398 | 30e3495c |
| t | f2352f28 | 37c71621 | 5cf0b028 | 40a015a7 |

The two CPU anchors must agree on the CPU family. `remap_pfn_range` and
`find_vma` must agree on the memory family when both appear. The three
combinations above are accepted; old CPU plus new memory is unobserved and
rejected. A different CRC for the same anchor, within one file or across
files, is always rejected. Consistent duplicate declarations are allowed.

The first three anchors are required across the supplied modules. `find_vma`
remains optional to support a normal `conninfra.ko` input; when present its
CRC is validated. Supplying both `conninfra.ko` and `met.ko` checks all four.
Unrelated peer symbols are parsed but cannot select or change a family.

`early` is supported by the ten-module public dump of MIUI 14.0.6.0.TKPCNXM
at [commit 9714227175010692d8374082ae98075abf18107c](https://github.com/leddaz-dump-stash/redmi_chopin_dump/tree/9714227175010692d8374082ae98075abf18107c).
Its [system properties](https://github.com/leddaz-dump-stash/redmi_chopin_dump/blob/9714227175010692d8374082ae98075abf18107c/system/system/build.prop)
identify Android 13 / SDK 33, while its
[vendor properties](https://github.com/leddaz-dump-stash/redmi_chopin_dump/blob/9714227175010692d8374082ae98075abf18107c/vendor/build.prop)
identify Android 12 / SDK 31. Those properties document the source; they
are not installation selectors. Git blob sizes and hashes tied all ten
modules to that same commit. This is a public maintainer dump, without an
independent Xiaomi signature or complete official-ROM hash validation.

## Command and exit codes

```
chopin-abi-select MODULE.ko [MODULE.ko ...]
```

Success: stdout is exactly `legacy\n`, `early\n`, or `t\n`. It is printed
only after every input has been validated. Failures leave stdout empty and
start stderr with `ABI selection:`.

| Exit | Meaning |
| --- | --- |
| 0 | One accepted ABI combination |
| 2 | Missing or excessive arguments |
| 3 | Missing, unreadable, oversized or non-regular file |
| 4 | Unsupported or malformed ELF |
| 5 | Missing or malformed `__versions` |
| 6 | Unknown anchor CRC |
| 7 | Conflicting anchors or an unobserved CPU/memory combination |
| 8 | Incomplete required anchors |

Inputs are bounded to 32 regular files, each at most 64 MiB. Symlinks to
regular files are accepted. FIFO, block and character device data are
never read. The program does not invoke `su`, load modules, write blocks,
patch CRCs or disable kernel symbol version checking.

## Cloud tests and installation

`host-test.py` runs a supplied compiled binary. It does not compile locally.
The original 60 synthetic ELF and file-error cases are preserved unchanged;
25 cases add the observed four-anchor `early` signature, split-file evidence,
section offsets, peers and conflicting or unobserved combinations. The
JSON retains `status=PASS_REAL_COMPILED_SELECTOR_SYNTHETIC_ELF_FILE_CASES_ONLY`
on a fully successful run and adds `profiles` / `supported_profiles`,
`legacy_case_count`, `third_family_case_count` and `generator_sha256`
(the test generator file hash). The draft itself has not yet been compiled
or run; the previous two-family CI result remains separate evidence.

Run the file cases against both a host build with undefined-behavior checks
and a static AArch64 `-Os` build under `qemu-aarch64` in disposable cloud CI.
The fixtures contain generated ELF headers and CRC constants, without any
vendor binary bytes. Passing these tests proves parser and selection behavior,
not boot, driver, battery or universal firmware compatibility.

Place independently built and checked payloads at `images/legacy/Image`,
`images/early/Image` and `images/t/Image`. After normal AK3 split and backup,
select the appropriate Image, retain the phone's ramdisk and DTB, and continue
the normal repack, write and readback path. Recovery must first make its
vendor module directories readable. Missing evidence or unknown ABI must
stop installation before any write; never default to a profile by ROM name.

The `early` kernel build hypothesis is CPU ABI backport only, without the
anon_vma/rmap ABI backport. A real compiled early payload must match all 581
unique vmlinux imports and 108 peer imports from the pinned sample before it
is packaged. Full-system acceptance, including Android 11, is separate.

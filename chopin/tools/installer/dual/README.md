This package contains three kernel Images. The directory name `dual` is kept
for source history; the package is no longer limited to two vendor ABIs.

- `Image` is the `t` ABI payload.
- `images/legacy/Image` is the older vendor ABI payload.
- `images/early/Image` has the newer CPU interface and older memory interface,
  observed in MIUI 14.0.6 vendor modules.
- `tools/chopin-abi-select` reads ELF64 `__versions` records from conninfra.ko
  and met.ko. Framework Android/SDK version is not the selection criterion.

The ordinary AK3 split/repack path keeps the selected phone's own header,
ramdisk and DTB. It backs up the active boot partition before ABI selection.
The `t` branch keeps the root Image in place; it never copies a file onto
itself. The legacy and early branches copy only their matching payload.
Unknown, conflicting, missing or unreadable module ABIs stop before boot
writing. A missing matching Image also stops rather than selecting a default.

When vendor modules are unavailable in Recovery, the selector can temporarily
mount vendor/odm and their module partitions read-only. It releases only mounts
it created. It does not remount an existing Android vendor mount or change
another boot slot. Root does not bypass UFS hardware write protection.

Magisk/the original manager module entry is retained from the checked minimal
installer. Kernel Flasher and Recovery use the standard ZIP updater entry.
Successful synthetic ELF/Shell/file tests do not prove a physical Recovery
flash, every custom ROM, decryption, camera, power use or an unknown vendor ABI.
There is no claim that a real MIUI11 sample has been tested.

The file-test workflow compiles the actual current selector C source for host
and static AArch64, runs its 85 ELF cases on both, then runs 43 isolated Shell
cases and the unchanged 38 common installer cases. No previous selector binary
or report is accepted as evidence for the new source.

`build.py` requires `--t-candidate`, `--legacy-candidate`, `--early-candidate`
and each corresponding `--*-proof` containing 13 independent checks. It also
requires `--base-repo`, `--ak3`, `--licenses`, `--selector-evidence`, `--fixtures`,
`--source-commit` and `--output`. The evidence and fixture directories come from
the same workflow run and carry that exact source commit. The early proof's
profile defaults to `early`; `--early-proof-profile` accepts another explicit
label used by the independent checker.

The manager buildVersion comes from the actual three kernel manifests; all
three must agree. It is written to the package metadata and module receipt,
rather than being fixed to a past CI version. Exactly three Image payloads
are stored, and no manager APK is included.

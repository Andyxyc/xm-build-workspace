This installer is for chopin Android 13 across compatible firmware variants.
It keeps the current slot, backs up boot, preserves its own DTB/ramdisk,
propagates write errors and checks the actual write result. It does not bind
the package to a firmware increment, vendor-module hashes or a fixed header.
Old failed-install records are preserved as evidence and never permanently
block a later user-initiated installation.

The r10 kernel Image f280e96e failed a real boot test and was withdrawn.
Do not package that Image with these simplified scripts. Installer success
on ordinary files does not establish that a kernel will boot.

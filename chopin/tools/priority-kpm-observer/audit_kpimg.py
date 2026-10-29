#!/usr/bin/env python3
"""Read-only ELF/raw consistency and actual KP export-table binding."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from make_profile import KPIMG_SHA

if sys.flags.optimize:
    raise RuntimeError("Assertions must be enabled; refusing an optimized Python run")


def audit(raw, elf):
    assert hashlib.sha256(raw).hexdigest() == KPIMG_SHA, "not the paired kpimg"
    assert elf[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", elf, 18)[0] == 183
    shoff = struct.unpack_from("<Q", elf, 40)[0]
    es, num = struct.unpack_from("<HH", elf, 58)
    assert es == 64
    sections = [struct.unpack_from("<IIQQQQIIQQ", elf, shoff+i*es) for i in range(num)]
    symbols = {}
    for sh in sections:
        if sh[1] != 2:
            continue
        strings_sh = sections[sh[6]]
        strings = elf[strings_sh[4]:strings_sh[4]+strings_sh[5]]
        for p in range(sh[4], sh[4]+sh[5], 24):
            n, info, other, sec, va, size = struct.unpack_from("<IBBHQQ", elf, p)
            name = strings[n:].split(b"\0", 1)[0].decode()
            if name:
                symbols.setdefault(name, []).append((va, size, info, sec))

    def unique(name):
        assert len(symbols.get(name, [])) == 1, "missing/duplicate ELF symbol: "+name
        return symbols[name][0]

    base = unique("_link_base")[0]
    compared = 0
    for sh in sections:
        if sh[2] & 2 and sh[1] == 1 and sh[5]:
            off = sh[3]-base
            assert 0 <= off and off+sh[5] <= len(raw)
            assert raw[off:off+sh[5]] == elf[sh[4]:sh[4]+sh[5]], "ELF/raw loadable bytes differ"
            compared += sh[5]
    start, end = unique("_kp_symbol_start")[0], unique("_kp_symbol_end")[0]
    assert base <= start < end <= base+len(raw) and (end-start) % 48 == 0
    exports = {}
    for va in range(start, end, 48):
        addr, h = struct.unpack_from("<QQ", raw, va-base)
        n = raw[va-base+16:va-base+48]
        assert b"\0" in n and h == 0
        name = n.split(b"\0", 1)[0].decode()
        assert n == name.encode()+b"\0"*(32-len(name))
        assert name and name not in exports
        exports[name] = {"entry_link_va": hex(va), "target_link_va": hex(addr)}
    expected = {}
    for name in ["kallsyms_lookup_name", "kallsyms_on_each_symbol"]:
        va, size, info, sec = unique(name)
        assert size == 8 and info & 15 == 1, "expected function-pointer variable"
        assert name in exports and int(exports[name]["target_link_va"], 16) == va
        assert raw[va-base:va-base+8] == b"\0"*8
        expected[name] = {**exports[name], "elf_size": size,
                          "elf_kind": "STT_OBJECT function-pointer variable",
                          "initial_slot_zero": True}
    ctl_va, ctl_size, _, _ = unique("module_control0")
    ctl = raw[ctl_va-base:ctl_va-base+ctl_size]
    # Exact opcodes independently decoded from this paired artifact, not a
    # guessed ABI from a newer header: load ctl0; pass x0/x1/w2; BLR; keep x0.
    frame = bytes.fromhex("633e40f9e2031a2a601e40f9e10319aa630040f960003fd6e30300aa")
    assert ctl.count(frame) == 1, "paired callback call-frame differs"
    callback = ctl_va+ctl.index(frame)
    return {"status": "PASS_STATIC_ACTUAL_PAIRED_KPIMG", "raw_sha256": KPIMG_SHA,
            "elf_sha256": hashlib.sha256(elf).hexdigest(), "link_base": hex(base),
            "loadable_progbits_compared": compared, "export_entries": len(exports),
            "required_exports": expected,
            "actual_ctl0_frame": {
                "module_control0_link_va": hex(ctl_va), "module_control0_bytes": ctl_size,
                "callback_block_link_va": hex(callback), "raw_offset": hex(callback-base),
                "bytes_hex": frame.hex(),
                "instructions": ["ldr x3, [x19, #0x78]", "mov w2, w26", "ldr x0, [x19, #0x38]",
                                 "mov x1, x25", "ldr x3, [x3]", "blr x3", "mov x3, x0"],
                "interpretation": "actual module callback: ctl_args x0, out_msg x1, outlen w2; x0 return retained"},
            "scope": "file binary export/data binding; not runtime-loaded pointer values"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kpimg", type=Path, required=True)
    ap.add_argument("--elf", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    result = audit(a.kpimg.read_bytes(), a.elf.read_bytes())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()

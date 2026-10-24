#!/usr/bin/env python3
"""Restore the real data storage directly written by the stock WLAN module."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
source=Path(__file__).parent/'vendor_refcnt_trace.c'
dest=root/'net/core/chopin_vendor_refcnt_trace.c'
assert not dest.exists(), 'Do not overwrite an existing implementation'
dest.write_bytes(source.read_bytes())
header=root/'net/core/chopin_vendor_refcnt_trace.h'
assert not header.exists(), 'Do not overwrite an existing public layout'
header.write_bytes((Path(__file__).parent/'vendor_refcnt_trace.h').read_bytes())
file=root/'net/core/Makefile'
text=file.read_text()
assert 'chopin_vendor_refcnt_trace' not in text
file.write_text(text+'\n# Real legacy WLAN reference-trace storage, populated by ROM vendor modules.\nobj-y += chopin_vendor_refcnt_trace.o\n')
print('Restored actual stock WLAN ring storage; added no trace hooks or polling')

"""Regression for the real failed Image's branch beyond EOF and empty payload."""
import struct
from verify_image_entry import inspect,inspect_kpm

def image(size,target):
    b=bytearray(size);b[56:60]=b'ARMd';struct.pack_into('<I',b,0,0x14000000|target//4)
    if target+64<=size:b[target:target+64]=bytes.fromhex('1f2003d5')*16
    return bytes(b)

def reject(fn,label):
    try:fn()
    except ValueError:print('PASS rejected '+label)
    else:raise AssertionError('Accepted '+label)

assert inspect(image(256,128))['entry_offset']==128
reject(lambda:inspect(image(0x21a6090,0x21a7000)),'actual failed entry geometry')
reject(lambda:inspect(image(128,128)),'entry exactly at EOF')
reject(lambda:inspect(image(256,128)[:128]+bytes(128)),'zero executable entry')
reject(lambda:inspect_kpm(image(256,128),image(256,128),b'\xaa'+bytes(15)),'16-byte placeholder KPM payload')
print('PASS genuine backed entry; no device commands')

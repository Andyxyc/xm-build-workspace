"""Reject an ARM64 Image whose first branch has no backed executable bytes."""
from pathlib import Path
import argparse,hashlib,json,struct

def inspect(image):
    if len(image)<68 or image[56:60]!=b'ARMd':
        raise ValueError('Missing complete ARM64 Image header')
    off=4 if image[:2]==b'MZ' else 0
    insn=struct.unpack_from('<I',image,off)[0]
    if insn&0xfc000000!=0x14000000:
        raise ValueError('ARM64 Image entry is not an unconditional branch')
    imm=insn&0x3ffffff
    if imm&(1<<25):imm-=1<<26
    target=off+4*imm
    if target<64 or target+64>len(image):
        raise ValueError(f'Entry target 0x{target:x} is outside file-backed code (file end 0x{len(image):x})')
    code=image[target:target+64]
    if not any(code) or code==b'\xff'*64:
        raise ValueError('ARM64 Image entry targets empty bytes')
    return dict(image_sha256=hashlib.sha256(image).hexdigest(),image_bytes=len(image),branch_instruction=hex(insn),branch_offset=off,entry_offset=target,entry_bytes_sha256=hashlib.sha256(code).hexdigest())

def inspect_kpm(image,before,kpimg):
    r=inspect(image);original=inspect(before)
    if len(kpimg)<=4096+64 or kpimg[:8]!=b'KP1158\0\0':
        raise ValueError('KPM requires a complete KP1158 payload including its executable entry')
    aligned=(len(before)+4095)//4096*4096
    if image[aligned:aligned+64]!=kpimg[:64]:
        raise ValueError('KPM header/version does not match the pinned payload')
    if len(image)<aligned+len(kpimg):
        raise ValueError('KPM payload is truncated')
    if r['entry_offset']!=aligned+4096 or image[aligned+4096:aligned+4096+64]!=kpimg[4096:4096+64]:
        raise ValueError('KPM branch does not target the actual pinned executable entry')
    size,kpsize=struct.unpack_from('<qq',image,aligned+64+8)
    if size!=len(before) or kpsize!=len(kpimg):
        raise ValueError('KPM saved image/payload lengths disagree')
    r.update(before_sha256=original['image_sha256'],kpimg_sha256=hashlib.sha256(kpimg).hexdigest(),kpimg_bytes=len(kpimg),kpimg_offset=aligned,kp_version_bytes=kpimg[8:12].hex(),status='PASS_ENTRY_AND_COMPLETE_PINNED_KPM_PAYLOAD_ONLY',hardware_validated=False)
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image',type=Path);p.add_argument('--before',type=Path);p.add_argument('--kpimg',type=Path);p.add_argument('--report',type=Path)
    a=p.parse_args();image=a.image.read_bytes()
    if bool(a.before)!=bool(a.kpimg):p.error('--before and --kpimg must be supplied together')
    r=inspect_kpm(image,a.before.read_bytes(),a.kpimg.read_bytes()) if a.before else inspect(image)
    if a.report:
        if a.report.exists():raise FileExistsError('Keep earlier verification evidence')
        a.report.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r,indent=2))

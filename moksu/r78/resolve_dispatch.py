"""Resolve the two reviewed independent additions in KSU32709 dispatch.c."""
import re

def resolve(data: bytes, old_custom: bytes, upstream: bytes) -> bytes:
    text=data.decode('utf-8')
    pattern=re.compile(r'^<<<<<<< [^\n]+\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]+\n', re.M|re.S)
    matches=list(pattern.finditer(text))
    if len(matches)!=2:
        raise ValueError('Expected precisely the two reviewed dispatch additions')
    def union(match):
        left,right=match.group(1),match.group(2)
        if 'static int do_moksu_stealth_get' in left and 'static int do_lookup_symbols' in right:
            if not left.endswith('    return ksu_stealth_set(cmd.enabled == 1);\n') or not right.endswith('    return ret;\n'):
                raise ValueError('Unexpected handler conflict boundaries')
            return left+'}\n\n'+right
        if '.cmd = KSU_IOCTL_STEALTH_GET,' in left and '.cmd = KSU_IOCTL_LOOKUP_SYMBOLS,' in right:
            if left.count('.perm_check = manager_or_root')!=2 or right.count('.perm_check = only_root')!=1:
                raise ValueError('Permission guard changed')
            return left+'    },\n    {\n'+right
        raise ValueError('Unreviewed conflict')
    result=pattern.sub(union,text)
    if any(marker in result for marker in ('<<<<<<<','=======','>>>>>>>')):
        raise ValueError('Unresolved markers')
    for name,origin in [('do_moksu_stealth_get',old_custom),('do_moksu_stealth_set',old_custom),('do_lookup_symbols',upstream)]:
        block=re.search(r'^static int '+name+r'\(void __user \*arg\)\n\{.*?^\}',origin.decode(),re.M|re.S)
        if not block or block.group(0) not in result:
            raise ValueError('Handler changed: '+name)
    for op in ('STEALTH_GET','STEALTH_SET','LOOKUP_SYMBOLS'):
        if result.count('.cmd = KSU_IOCTL_'+op+',')!=1:
            raise ValueError('Duplicate or missing operation: '+op)
    return result.encode()

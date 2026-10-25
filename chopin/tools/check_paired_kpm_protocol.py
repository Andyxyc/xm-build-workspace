"""Compile the actual KP protocol/registration functions against bounded host mocks."""
from pathlib import Path
import hashlib,json,re,subprocess,sys,tempfile
kp=Path(sys.argv[1]);source=(kp/'kernel/patch/sukisu/sukisu.c').read_text(encoding='utf-8')
header=(kp/'kernel/patch/sukisu/supercall.h').read_text(encoding='utf-8')
defines='\n'.join(l for l in header.splitlines() if l.startswith('#define SUKISU_'))
a=source.index('static void before_supercall(');b=source.index('\nint sukisu_kpm_supercall_install',a)
handler=source[a:b];installer=source[b:]
prefix=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PSR_MODE_EL1h 5
struct pt_regs { unsigned long regs[31]; unsigned long pstate; };
#define processor_mode(r) ((r)->pstate & 15)
typedef struct { unsigned long arg0; long ret; int skip_origin; } hook_fargs1_t;
static int dispatched, has_syscall_wrapper, endpoint, hook_result, hooks;
static unsigned long hooked;
static long dispatch(unsigned long op,unsigned long a,unsigned long b,unsigned long c,unsigned long d) {
    ++dispatched; assert(op==3 && a==11 && b==22 && c==33 && d==44); return 17;
}
static unsigned long kallsyms_lookup_name(const char *name) {
    if (!strcmp(name,"ksu_kpm_bridge_trampoline")) return endpoint ? 0x4000 : 0;
    if (!strcmp(name,"__arm64_sys_truncate")) return has_syscall_wrapper ? 0x8000 : 0;
    return 0;
}
static int hook_wrap1(void *addr, void (*before)(hook_fargs1_t*,void*),void *after,void *data) {
    (void)before;(void)after;(void)data; ++hooks; hooked=(unsigned long)addr;return hook_result;
}
'''
main=r'''
int main(int argc,char **argv) {
    int mode=argc>1?atoi(argv[1]):0;
    struct pt_regs regs={0};hook_fargs1_t args={0};
    regs.pstate=PSR_MODE_EL1h;regs.regs[0]=SUKISU_KPM_SUPERCALL_MAGIC;
    regs.regs[1]=3;regs.regs[2]=11;regs.regs[3]=22;regs.regs[4]=33;regs.regs[5]=44;
    regs.regs[6]=SUKISU_KPM_SUPERCALL_MAGIC2;regs.regs[7]=SUKISU_KPM_SUPERCALL_MAGIC3;
    regs.regs[8]=SUKISU_KPM_ABI_VERSION;args.arg0=(unsigned long)&regs;
    before_supercall(&args,0);assert(args.skip_origin==1 && args.ret==17 && dispatched==1);
    for(int i=0;i<31;i++) {
        if(i>=1 && i<=5)continue;
        unsigned long saved=regs.regs[i];regs.regs[i]^=1;args.skip_origin=0;args.ret=123;
        before_supercall(&args,0);assert(dispatched==1);
        if(i==0)assert(args.skip_origin==0 && args.ret==123);
        else assert(args.skip_origin==1 && args.ret==-EPROTO);
        regs.regs[i]=saved;
    }
    regs.pstate=0;args.skip_origin=0;args.ret=123;before_supercall(&args,0);
    assert(args.skip_origin==0 && args.ret==123 && dispatched==1);
    endpoint=mode==0 || mode==3;has_syscall_wrapper=mode==1;hook_result=mode==3?-EIO:0;
    int rc=sukisu_kpm_supercall_install();
    if(mode==2)assert(rc==-EOPNOTSUPP && hooks==0);
    else if(mode==3)assert(rc==-EIO && hooks==1);
    else {
        assert(rc==0 && hooks==1 && hooked==(endpoint?0x4000:0x8000));
        assert(sukisu_kpm_supercall_install()==0 && hooks==1);
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='kp-paired-protocol-') as temp:
    root=Path(temp);c=root/'check.c';exe=root/'check';c.write_text(prefix+'\n'+defines+'\n'+handler+'\n'+installer+'\n'+main)
    q=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],capture_output=True)
    assert q.returncode==0,q.stderr.decode()
    for mode in range(4):subprocess.run([str(exe),str(mode)],check=True)
report=dict(status='PASS_ACTUAL_KP_FRAMING_AND_ENDPOINT_REGISTRATION_HOST_MOCKS',scope='NO_IMAGE_NO_DEVICE_HOST_MOCKS',source_sha256=hashlib.sha256(source.encode()).hexdigest(),framing_cases=28,registration_cases=4,el0_passthrough=True,no_legacy_syscall_prototype_cast=True,hardware_verified=False)
Path('paired-kpm-protocol.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

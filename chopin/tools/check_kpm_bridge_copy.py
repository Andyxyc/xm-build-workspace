"""Compile the actual current KPM copy/dispatch functions with bounded host mocks."""
from pathlib import Path
import hashlib,json,os,re,subprocess,tempfile
root=Path(os.environ['WORKSPACE'])/'android-kernel'
source=(root/'KernelSU/kernel/extension/kpm/kpm.c').read_text()
start=source.index('static int chopin_kpm_copy_string(')
body=source[start:source.index('/* The top-level extension.c',start)]
headers=list((root/'KernelSU/uapi').rglob('*.h'))+list((root/'KernelSU/kernel').rglob('*.h'))
definition=None
for p in headers:
    s=p.read_text(errors='replace')
    m=re.search(r'struct ksu_kpm_cmd\s*\{.*?\};',s,re.S)
    if m:definition=m.group();break
assert definition is not None
prefix=r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t __u64;
typedef uint32_t __u32;
#define __aligned_u64 __u64 __attribute__((aligned(8)))
#define __user
#define GFP_KERNEL 0
#define VERIFY_WRITE 1
#define access_ok(mode,p,n) ((p)!=NULL)
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
#define KPM_NAME_LEN 32
#define KPM_ARGS_LEN 1024
#define KPM_PATH_LEN 1024
#define KPM_INFO_LEN 256
#define SUKISU_KPM_OUTPUT_MAX 4096
#define SUKISU_KPM_LOAD 1
#define SUKISU_KPM_UNLOAD 2
#define SUKISU_KPM_NUM 3
#define SUKISU_KPM_LIST 4
#define SUKISU_KPM_INFO 5
#define SUKISU_KPM_CONTROL 6
#define SUKISU_KPM_VERSION 7
#define SUKISU_KPM_LOAD_EVENT 8
static unsigned char output[8192];
static size_t capacity, copied;
static int fault, alloc_fault, bridge_error, bridge_calls;
static void *kzalloc(size_t n,int flags) { (void)flags;return alloc_fault?NULL:calloc(1,n); }
static void *kmalloc(size_t n,int flags) { (void)flags;return alloc_fault?NULL:malloc(n); }
#define kfree free
static long strncpy_from_user(char *out,const char *in,size_t n) {
    if(!in)return -EFAULT;
    size_t len=strnlen(in,n);memcpy(out,in,len);if(len<n)out[len]=0;return len;
}
static size_t copy_from_user(void *out,const void *in,size_t n) {
    if(!in)return n;memcpy(out,in,n);return 0;
}
static size_t copy_to_user(void *out,const void *in,size_t n) {
    if(!out)return n;
    if(out==output) { assert(n<=capacity);copied=n;if(fault)return n; }
    memcpy(out,in,n);return 0;
}
static long sukisu_kpm_bridge(unsigned long op,unsigned long a,unsigned long b,unsigned long c,unsigned long d) {
    (void)c;(void)d;++bridge_calls;if(bridge_error)return bridge_error;
    if(op==SUKISU_KPM_NUM)return 2;
    if(op==SUKISU_KPM_VERSION || op==SUKISU_KPM_LIST) {
        assert(a && b>0 && b<=4096);int n=snprintf((char *)a,b,"0.13.9 (probe)");return n>=(long)b?-ENOBUFS:n;
    }
    return 0;
}
'''
main=r'''
int main(void) {
    static const unsigned caps[]={0,1,4,256,1024,4096,4097};
    int result=123;
    for(unsigned i=0;i<sizeof(caps)/sizeof(caps[0]);i++) {
        capacity=caps[i];copied=0;memset(output,0xa5,sizeof(output));
        struct ksu_kpm_cmd cmd={.control_code=SUKISU_KPM_VERSION,.arg1=(uintptr_t)output,.arg2=capacity,.result_code=(uintptr_t)&result};
        assert(do_kpm(&cmd)==0);
        if(!capacity || capacity>4096)assert(result==-EINVAL && copied==0);
        else if(capacity<sizeof("0.13.9 (probe)"))assert(result==-ENOBUFS && copied==0);
        else assert(result==0 && copied==sizeof("0.13.9 (probe)") && !strcmp((char *)output,"0.13.9 (probe)") && output[sizeof("0.13.9 (probe)")]==0xa5);
    }
    struct ksu_kpm_cmd cmd={.control_code=SUKISU_KPM_VERSION,.arg1=(uintptr_t)output,.arg2=1024,.result_code=(uintptr_t)&result};
    capacity=1024;fault=1;assert(do_kpm(&cmd)==0 && result==-EFAULT);fault=0;
    bridge_error=-EPROTO;copied=0;assert(do_kpm(&cmd)==0 && result==-EPROTO && copied==0);bridge_error=0;
    alloc_fault=1;assert(do_kpm(&cmd)==0 && result==-ENOMEM);alloc_fault=0;
    cmd.result_code=0;assert(do_kpm(&cmd)==-EFAULT);assert(do_kpm(NULL)==-EFAULT);
    cmd.result_code=(uintptr_t)&result;cmd.control_code=999;assert(do_kpm(&cmd)==0 && result==-EOPNOTSUPP);
    /* CI41095 ksud falls back to LOAD only on EOPNOTSUPP, not EINVAL.
     * A paired ABI1 runtime must not receive the unsupported ABI2 operation. */
    cmd.control_code=SUKISU_KPM_LOAD_EVENT;cmd.arg1=0;cmd.arg2=0;
    int event_before=bridge_calls;
    assert(do_kpm(&cmd)==0 && result==-EOPNOTSUPP && bridge_calls==event_before);
    char valid_path[]="/data/local/tmp/chopin-test.kpm";
    cmd.control_code=SUKISU_KPM_LOAD;cmd.arg1=(uintptr_t)valid_path;
    assert(do_kpm(&cmd)==0 && result==0 && bridge_calls==event_before+1);
    char long_name[2048];memset(long_name,'x',sizeof(long_name));
    cmd.control_code=SUKISU_KPM_LOAD;cmd.arg1=(uintptr_t)long_name;cmd.arg2=0;
    int before=bridge_calls;assert(do_kpm(&cmd)==0 && result==-ENAMETOOLONG && bridge_calls==before);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='kpm-current-copy-') as temp:
    d=Path(temp);c=d/'test.c';exe=d/'test';c.write_text(prefix+'\n'+definition+'\n'+body+'\n'+main)
    q=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Wno-misleading-indentation',str(c),'-o',str(exe)],capture_output=True)
    assert q.returncode==0,q.stderr.decode()
    subprocess.run([str(exe)],check=True)
report=dict(status='PASS_CURRENT_KPM_ACTUAL_COPY_AND_DISPATCH_FUNCTIONS_HOST_MOCKS',scope='NO_KERNEL_NO_DEVICE_HOST_MOCKS',capacities=[0,1,4,256,1024,4096,4097],error_cases=['copy-fault','bridge-error','allocation-failure','null-result','null-command','unknown-op','truncated-path','ABI1-event-EOPNOTSUPP-no-bridge-call','ordinary-load-after-event-fallback'],source_sha256=hashlib.sha256(source.encode()).hexdigest(),hardware_verified=False)
Path('kpm-version-copy-tests.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

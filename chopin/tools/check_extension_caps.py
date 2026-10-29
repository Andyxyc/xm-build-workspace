"""Compile actual extension registry/dispatcher with bounded Linux host mocks.

Run after update_ci41098.py. No kernel/ADB/phone operations. Backend callbacks,
kernel locks/bitmaps and copy_{from,to}_user are mocked; the registry, handler
declarations, UAPI layouts and extension dispatcher are copied from the actual
patched source without rewriting their logic. --prepare-only never compiles.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile


def extract_braced(source, needle):
    match = re.search(r'^' + re.escape(needle) + r'\s*\{', source, re.M)
    assert match is not None, needle
    start = match.start()
    brace = source.index('{', start)
    depth = 1
    at = brace + 1
    while depth:
        if source[at] == '{':
            depth += 1
        elif source[at] == '}':
            depth -= 1
        at += 1
    assert source[at] == ';'
    return source[start:at + 1]


def no_includes(source):
    return re.sub(r'^\s*#include[^\n]*\n', '', source, flags=re.M)


PREFIX = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint64_t __u64;
typedef uint32_t __u32;
#define __user
#define __init
#define __exit
#define __read_mostly
/* This shared supercall bit is not extension implementation logic. */
#define KSU_FEATURE_FLAG_SUPPORTED (1u << 0)
#define DEFINE_MUTEX(name) int name
#define DECLARE_BITMAP(name,n) unsigned long name[((n)+63)/64]
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_wmb() ((void)0)
#define WARN_ON_ONCE(x) (!!(x))
#define set_bit(n,b) ((b)[(n)/64] |= 1ul << ((n)%64))
#define clear_bit(n,b) ((b)[(n)/64] &= ~(1ul << ((n)%64)))
#define test_bit(n,b) (!!((b)[(n)/64] & (1ul << ((n)%64))))
#define for_each_set_bit(i,b,n) for ((i)=0;(i)<(n);(i)++) if (test_bit((i),(b)))
static void mutex_lock(int *lock) { assert(*lock==0);*lock=1; }
static void mutex_unlock(int *lock) { assert(*lock==1);*lock=0; }
struct kernel_param { int unused; };
struct kernel_param_ops { unsigned flags;int (*set)(const char *,const struct kernel_param *); };
#define KERNEL_PARAM_OPS_FL_NOARG 1
#define module_param_cb(name,ops,arg,perm) \
    static const void *keep_param_##name __attribute__((unused)) = (ops)
static void discard_log(const char *fmt,...) { (void)fmt; }
#define pr_err(...) discard_log(__VA_ARGS__)
#define pr_warn(...) discard_log(__VA_ARGS__)
#define pr_info(...) discard_log(__VA_ARGS__)
static int kstrtou64(const char *s,unsigned base,u64 *value) {
    char *end=NULL;errno=0;unsigned long long n=strtoull(s,&end,base);
    if(errno || !*s || !end || *end || s[0]=='-')return -EINVAL;
    *value=n;return 0;
}
static int kstrtou32(const char *s,unsigned base,u32 *value) {
    u64 n;int ret=kstrtou64(s,base,&n);if(ret || n>UINT32_MAX)return -EINVAL;
    *value=(u32)n;return 0;
}
static long strscpy(char *dst,const char *src,size_t cap) {
    size_t n=strlen(src);if(!cap)return -E2BIG;
    size_t take=n<cap?n:cap-1;memcpy(dst,src,take);dst[take]=0;
    return n<cap?(long)n:-E2BIG;
}
static const void *bad_user=(const void *)(uintptr_t)1;
static const void *copy_in_fault_ptr,*copy_out_fault_ptr;
static size_t copy_from_user(void *dst,const void *src,size_t n) {
    if(!src || src==bad_user || src==copy_in_fault_ptr)return n;
    memcpy(dst,src,n);return 0;
}
static size_t copy_to_user(void *dst,const void *src,size_t n) {
    if(!dst || dst==bad_user || dst==copy_out_fault_ptr)return n;
    memcpy(dst,src,n);return 0;
}
'''


BACKENDS = r'''
/* Deliberately simple backend stubs; these do not validate subsystem behavior. */
static u64 state[KSU_EXTENSION_MAX];
static unsigned get_calls,set_calls,io_calls,wipe_calls,force_calls;
static int get_error,set_error;
static u32 last_id;
static void *last_io;
static int mock_get(u32 id,u64 *value) {
    get_calls++;last_id=id;
    if(get_error)return get_error;
    *value=state[id];return 0;
}
static int mock_set(u32 id,u64 value) {
    set_calls++;last_id=id;if(set_error)return set_error;
    state[id]=value;return 0;
}
static int mock_io(u32 id,void *raw) {
    io_calls++;last_id=id;last_io=raw;
    return !raw || raw==bad_user?-EFAULT:42;
}
static int mock_wipe(u32 id) { wipe_calls++;last_id=id;state[id]=0;return 0; }
static void mock_forced(u32 id,u64 value) { force_calls++;last_id=id;state[id]=value; }
static const struct ksu_extension_handler_ops ksu_extension_kpm_ops={.get=mock_get};
static const struct ksu_extension_handler_ops ksu_extension_dynamic_manager_ops={.get=mock_get,.set=mock_set};
static const struct ksu_extension_handler_ops ksu_extension_susfs_ops={.get=mock_get};
#define ksu_extension_kpm_io mock_io
#define ksu_extension_kpm_apply_forced mock_forced
#define ksu_extension_cpu_spoof_io mock_io
#define ksu_extension_umount_paths_io mock_io
#define ksu_extension_umount_paths_wipe mock_wipe
#define ksu_extension_dynamic_manager_io mock_io
#define ksu_extension_version_spoof_io mock_io
#define ksu_extension_version_spoof_wipe mock_wipe
'''


TESTS = r'''
static unsigned assertions;
#define CHECK(x) do { assertions++;assert(x); } while(0)
static struct ksu_extension_cmd command(u32 id,u32 op,u32 api) {
    return (struct ksu_extension_cmd){.id=id,.op=op,.api_version=api,.supported=0xdeadbeef,.value=0xa5};
}
int main(void) {
    CHECK(sizeof(struct ksu_extension_cmd)==32);
    CHECK(sizeof(struct ksu_extension_desc)==48);
    CHECK(offsetof(struct ksu_extension_cmd,value)==16);
    CHECK(offsetof(struct ksu_extension_cmd,user_ptr)==24);
    CHECK(KSU_EXTENSION_API_VERSION==2);
    ksu_extension_init();state[KSU_EXTENSION_KPM]=1;
    ksu_extension_register_all();
    const char *names[]={"kpm","cpu_spoof","umount_paths","dynamic_manager","susfs","version_spoof"};
    const u32 semantic[]={0,0,0,KSU_EXTENSION_FLAG_STICKY|KSU_EXTENSION_FLAG_PERSIST,KSU_EXTENSION_FLAG_REBOOT,0};
    CHECK(KSU_EXTENSION_MAX==6);
    struct ksu_extension_desc desc;
    struct ksu_extension_cmd cmd;
    for(u32 i=0;i<KSU_EXTENSION_MAX;i++) {
        memset(&desc,0xa5,sizeof(desc));
        cmd=command(KSU_EXTENSION_ABI_PROBE_ID,KSU_EXTENSION_ENUM,0);
        cmd.user_ptr=(uintptr_t)&desc;cmd.value=i;
        CHECK(do_extension(&cmd)==0);
        CHECK(desc.id==i && !strcmp(desc.name,names[i]));
        CHECK(desc.caps==(KSU_FEATURE_FLAG_SUPPORTED|semantic[i]));
        CHECK(desc.min_api_version==0 && desc.forced==0);
        CHECK(cmd.id==i && cmd.api_version==2 && cmd.value==0 && cmd.supported==desc.caps);
        cmd=command(i,KSU_EXTENSION_GET,0);
        CHECK(do_extension(&cmd)==0);
        CHECK(cmd.api_version==2 && cmd.supported==(KSU_FEATURE_FLAG_SUPPORTED|semantic[i]));
        CHECK(cmd.value==state[i]);
    }
    cmd=command(KSU_EXTENSION_ABI_PROBE_ID,KSU_EXTENSION_ENUM,2);
    cmd.user_ptr=(uintptr_t)&desc;cmd.value=KSU_EXTENSION_MAX;
    CHECK(do_extension(&cmd)==-ENOENT);
    cmd.value=1ull<<32;CHECK(do_extension(&cmd)==-EINVAL);
    cmd.value=0;cmd.user_ptr=0;CHECK(do_extension(&cmd)==-EINVAL);
    cmd.user_ptr=(uintptr_t)bad_user;CHECK(do_extension(&cmd)==-EFAULT);
    cmd.user_ptr=(uintptr_t)&desc;cmd.id=0;CHECK(do_extension(&cmd)==-EINVAL);
    CHECK(ksu_extension_enumerate(0,NULL)==-EINVAL);
    CHECK(ksu_extension_enumerate(UINT32_MAX,&desc)==-ENOENT);
    cmd=command(KSU_EXTENSION_ABI_PROBE_ID,KSU_EXTENSION_ABI,0);
    CHECK(do_extension(&cmd)==0 && cmd.api_version==2 && cmd.value==0 && cmd.supported==0);
    cmd.id=0;CHECK(do_extension(&cmd)==-EINVAL);
    CHECK(do_extension(NULL)==-EFAULT);
    CHECK(do_extension((void *)bad_user)==-EFAULT);
    cmd=command(KSU_EXTENSION_ABI_PROBE_ID,KSU_EXTENSION_ABI,0);
    copy_in_fault_ptr=&cmd;CHECK(do_extension(&cmd)==-EFAULT);copy_in_fault_ptr=NULL;
    copy_out_fault_ptr=&cmd;CHECK(do_extension(&cmd)==-EFAULT);copy_out_fault_ptr=NULL;
    cmd=command(KSU_EXTENSION_ABI_PROBE_ID,KSU_EXTENSION_ENUM,2);
    cmd.user_ptr=(uintptr_t)&desc;cmd.value=0;
    copy_out_fault_ptr=&desc;CHECK(do_extension(&cmd)==-EFAULT);copy_out_fault_ptr=NULL;
    copy_out_fault_ptr=&cmd;CHECK(do_extension(&cmd)==-EFAULT);copy_out_fault_ptr=NULL;
    cmd=command(KSU_EXTENSION_MAX,KSU_EXTENSION_GET,2);CHECK(do_extension(&cmd)==-EINVAL);

    /* Current real declarations must not grow fake runtime toggle support. */
    for(u32 i=0;i<KSU_EXTENSION_MAX;i++) if(i!=KSU_EXTENSION_DYNAMIC_MANAGER) {
        cmd=command(i,KSU_EXTENSION_SET,2);CHECK(do_extension(&cmd)==-EOPNOTSUPP);
    }
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_SET,0);cmd.value=1;
    CHECK(do_extension(&cmd)==0 && cmd.api_version==2 && cmd.value==1 && cmd.supported==7);
    CHECK(state[KSU_EXTENSION_DYNAMIC_MANAGER]==1);
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_SET,0);cmd.value=0;
    copy_out_fault_ptr=&cmd;CHECK(do_extension(&cmd)==-EFAULT);copy_out_fault_ptr=NULL;
    CHECK(state[KSU_EXTENSION_DYNAMIC_MANAGER]==0); /* setter succeeded before reply copy */
    cmd=command(KSU_EXTENSION_KPM,KSU_EXTENSION_GET,0);
    get_error=-EIO;CHECK(do_extension(&cmd)==-EIO);get_error=0;
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_SET,2);
    set_error=-EBUSY;CHECK(do_extension(&cmd)==-EBUSY);set_error=0;
    cmd=command(KSU_EXTENSION_KPM,KSU_EXTENSION_GET,0);
    copy_out_fault_ptr=&cmd;CHECK(do_extension(&cmd)==-EFAULT);copy_out_fault_ptr=NULL;

    int payload=123;unsigned before=io_calls;
    cmd=command(KSU_EXTENSION_KPM,KSU_EXTENSION_IO,0);cmd.user_ptr=(uintptr_t)&payload;
    CHECK(do_extension(&cmd)==42 && io_calls==before+1 && last_io==&payload);
    CHECK(cmd.api_version==0); /* current IO path returns backend result, no header reply */
    cmd.user_ptr=0;CHECK(do_extension(&cmd)==-EFAULT);
    cmd=command(KSU_EXTENSION_UMOUNT_PATHS,KSU_EXTENSION_WIPE,0);
    before=wipe_calls;CHECK(do_extension(&cmd)==0 && wipe_calls==before+1);
    CHECK(cmd.api_version==0); /* WIPE likewise has no header reply */
    cmd=command(KSU_EXTENSION_SUSFS,KSU_EXTENSION_IO,2);cmd.user_ptr=(uintptr_t)&payload;
    CHECK(do_extension(&cmd)==-EOPNOTSUPP);
    cmd=command(KSU_EXTENSION_SUSFS,KSU_EXTENSION_WIPE,2);CHECK(do_extension(&cmd)==-EOPNOTSUPP);

    const struct ksu_extension_handler *original=extension_handlers[KSU_EXTENSION_CPU_SPOOF];
    struct ksu_extension_handler h=*original;
    CHECK(ksu_register_extension_handler(NULL)==-EINVAL);
    h.extension_id=KSU_EXTENSION_MAX;CHECK(ksu_register_extension_handler(&h)==-EINVAL);h=*original;
    h.ops=NULL;h.io_handler=NULL;CHECK(ksu_register_extension_handler(&h)==-EINVAL);h=*original;
    h.caps=KSU_FEATURE_FLAG_SUPPORTED;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    h.caps=KSU_EXTENSION_FLAG_FORCED;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    h.caps=KSU_EXTENSION_FLAG_STICKY;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    h=*original;h.ops=&ksu_extension_dynamic_manager_ops;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    h=*original;h.caps=KSU_EXTENSION_FLAG_PERSIST;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    h=*original;h.min_api_version=3;CHECK(ksu_register_extension_handler(&h)==-EINVAL);
    CHECK(extension_handlers[KSU_EXTENSION_CPU_SPOOF]==original);
    /* Upstream currently accepts reserved bits. Record, do not invent stricter validation. */
    h=*original;h.caps=1u<<20;CHECK(ksu_register_extension_handler(&h)==0);
    CHECK(ksu_register_extension_handler(original)==0);

    /* A future ABI2-only handler: all real dispatch paths must gate old callers. */
    h=*original;h.min_api_version=2;h.caps=KSU_EXTENSION_FLAG_STICKY|KSU_EXTENSION_FLAG_PERSIST;
    h.ops=&ksu_extension_dynamic_manager_ops;h.wipe=mock_wipe;
    CHECK(ksu_register_extension_handler(&h)==0);
    u64 value=999;u32 caps=999;
    CHECK(ksu_extension_get(h.extension_id,0,&value,&caps)==0 && caps==0 && value==0);
    for(u32 api=0;api<2;api++) {
        const u32 ops[]={KSU_EXTENSION_GET,KSU_EXTENSION_SET,KSU_EXTENSION_IO,KSU_EXTENSION_WIPE};
        for(unsigned i=0;i<sizeof(ops)/sizeof(ops[0]);i++) {
            cmd=command(h.extension_id,ops[i],api);cmd.user_ptr=(uintptr_t)&payload;
            unsigned s=set_calls,io=io_calls,w=wipe_calls;
            CHECK(do_extension(&cmd)==-EOPNOTSUPP);
            CHECK(set_calls==s && io_calls==io && wipe_calls==w);
        }
    }
    cmd=command(h.extension_id,KSU_EXTENSION_GET,2);CHECK(do_extension(&cmd)==0 && cmd.supported==7);
    cmd=command(h.extension_id,KSU_EXTENSION_SET,2);cmd.value=77;CHECK(do_extension(&cmd)==0 && cmd.value==77);
    cmd=command(h.extension_id,KSU_EXTENSION_IO,2);cmd.user_ptr=(uintptr_t)&payload;CHECK(do_extension(&cmd)==42);
    cmd=command(h.extension_id,KSU_EXTENSION_WIPE,2);CHECK(do_extension(&cmd)==0);
    h.min_api_version=1;
    CHECK(ksu_register_extension_handler(&h)==0);
    cmd=command(h.extension_id,KSU_EXTENSION_GET,0);CHECK(do_extension(&cmd)==0 && cmd.api_version==2);
    CHECK(ksu_register_extension_handler(original)==0);
    CHECK(ksu_extension_get(KSU_EXTENSION_MAX,0,&value,&caps)==-EINVAL);
    CHECK(ksu_extension_get(0,0,NULL,&caps)==-EINVAL);
    CHECK(ksu_extension_get(0,0,&value,NULL)==-EINVAL);

    const struct ksu_extension_handler *kpm_original=extension_handlers[KSU_EXTENSION_KPM];
    CHECK(ksu_unregister_extension_handler(KSU_EXTENSION_KPM)==0);
    CHECK(ksu_unregister_extension_handler(KSU_EXTENSION_KPM)==-ENOENT);
    CHECK(ksu_unregister_extension_handler(KSU_EXTENSION_MAX)==-EINVAL);
    cmd=command(KSU_EXTENSION_KPM,KSU_EXTENSION_GET,0);CHECK(do_extension(&cmd)==-EOPNOTSUPP);
    CHECK(ksu_extension_enumerate(0,&desc)==0 && desc.id==KSU_EXTENSION_CPU_SPOOF);
    CHECK(ksu_register_extension_handler(kpm_original)==0);

    /* Exercise actual force parser and ordering guard, not a mocked forced mask. */
    before=set_calls;extensions_registered=false;
    CHECK(force_extension_param_set("dynamic_manager:9,kpm:7",NULL)==0);
    CHECK(ksu_extension_is_forced(KSU_EXTENSION_DYNAMIC_MANAGER));
    ksu_extension_apply_forced();CHECK(set_calls==before);
    ksu_extension_register_all();ksu_extension_apply_forced();
    CHECK(state[KSU_EXTENSION_DYNAMIC_MANAGER]==9 && state[KSU_EXTENSION_KPM]==7 && force_calls==1);
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_GET,0);
    CHECK(do_extension(&cmd)==0 && cmd.supported==(7|KSU_EXTENSION_FLAG_FORCED) && cmd.value==9);
    CHECK(ksu_extension_enumerate(KSU_EXTENSION_DYNAMIC_MANAGER,&desc)==0 && desc.forced==1 && desc.caps==7);
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_SET,2);CHECK(do_extension(&cmd)==-EPERM);
    cmd=command(KSU_EXTENSION_DYNAMIC_MANAGER,KSU_EXTENSION_WIPE,2);CHECK(do_extension(&cmd)==-EPERM);
    CHECK(!ksu_extension_is_forced(KSU_EXTENSION_MAX));
    ksu_extension_exit();CHECK(ksu_extension_enumerate(0,&desc)==-ENOENT);
    printf("{\"assertions\":%u,\"registry_handlers\":6,\"extension_api\":2}\n",assertions);
    return 0;
}
'''


def build_source(root):
    ksu = root / 'KernelSU/kernel'
    paths = {
        'registry': ksu / 'extension/extension.c',
        'handler_header': ksu / 'extension/extension.h',
        'uapi': ksu / 'include/uapi/extension.h',
        'dispatcher': ksu / 'supercall/dispatch.c',
    }
    sources = {name: path.read_text(encoding='utf-8') for name, path in paths.items()}
    uapi = sources['uapi']
    assert re.search(r'^#define KSU_EXTENSION_API_VERSION\s+2u$', uapi, re.M)
    declarations = '\n'.join(extract_braced(uapi, name) for name in
                             ['enum ksu_extension_id', 'struct ksu_extension_desc', 'struct ksu_extension_cmd'])
    defines = '\n'.join(line for line in uapi.splitlines() if line.startswith('#define KSU_EXTENSION_'))
    assert all('\\' not in line for line in defines.splitlines())
    registry = no_includes(sources['registry'])
    assert 'extension_forced_values' in registry, 'Expected audited unity-build static name adaptation'
    dispatcher = sources['dispatcher']
    begin = dispatcher.index('/* Capability bits for a reply:')
    end = dispatcher.index('// IOCTL handlers mapping table', begin)
    dispatch_slice = dispatcher[begin:end]
    assert dispatch_slice.count('static int do_extension(') == 1
    c = '\n'.join([PREFIX, defines, declarations, no_includes(sources['handler_header']),
                   BACKENDS, registry, dispatch_slice, TESTS])
    return c, {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel-root', type=Path, default=None)
    p.add_argument('--report', type=Path, default=Path('extension-caps-tests.json'))
    p.add_argument('--prepare-only', type=Path, metavar='DIRECTORY')
    a = p.parse_args()
    root = a.kernel_root or Path(os.environ['WORKSPACE']) / 'android-kernel'
    c, hashes = build_source(root.resolve())
    report = {
        'status': 'PREPARED_ONLY_NOT_COMPILED',
        'scope': 'ACTUAL_SOURCE_FUNCTIONS_WITH_HOST_KERNEL_API_AND_SUBSYSTEM_CALLBACK_MOCKS',
        'source_sha256': hashes,
        'generated_c_sha256': hashlib.sha256(c.encode()).hexdigest(),
        'actual_registry_and_six_handler_declarations_used': True,
        'actual_dispatcher_and_uapi_used': True,
        'cases': ['actual-six-handler-enumeration-and-metadata', 'ABI-probe-id-and-copy-fault',
                  'legacy-api0', 'GET-SET-IO-WIPE-minimum-ABI-gates',
                  'register-SUPPORTED-FORCED-STICKY-PERSIST-minapi-invalid',
                  'missing-handler-and-enumeration-gaps', 'enum-null-bad-pointer-overflow-ENOENT',
                  'callback-errors-and-post-set-copy-failure', 'real-force-parser-order-guard-and-locking'],
        'observed_upstream_boundaries': ['reserved-caps-bits-currently-accepted',
                                         'IO-WIPE-return-backend-result-without-header-api-reply'],
        'subsystem_callbacks_verified': False,
        'locking_concurrency_verified': False,
        'kernel_compiled': False,
        'device_verified': False,
    }
    if a.prepare_only:
        a.prepare_only.mkdir(parents=True, exist_ok=True)
        (a.prepare_only / 'extension_caps_test.c').write_text(c, encoding='utf-8', newline='\n')
    else:
        with tempfile.TemporaryDirectory(prefix='chopin-extension-caps-') as temp:
            d = Path(temp); cfile = d / 'test.c'; exe = d / 'test'
            cfile.write_text(c, encoding='utf-8', newline='\n')
            compile_result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra',
                                             '-Wno-unused-parameter', '-Wno-unused-variable',
                                             '-Wno-unused-function', str(cfile), '-o', str(exe)],
                                            capture_output=True, text=True, timeout=60)
            assert compile_result.returncode == 0, compile_result.stderr
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stdout + result.stderr
            counts = json.loads(result.stdout.strip())
            assert counts['assertions'] >= 140 and counts['registry_handlers'] == 6
            report.update(status='PASS_ACTUAL_EXTENSION_REGISTRY_UAPI_DISPATCH_HOST_MOCK_CASES',
                          host_compile=True, host_execution=counts,
                          compile_warnings=compile_result.stderr)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

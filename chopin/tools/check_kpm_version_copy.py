"""Exercise the actual transformed VERSION branch, with a bounded copy backend."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

root = Path(os.environ['WORKSPACE']) / 'android-kernel'
source = (root / 'KernelSU/kernel/extension/kpm/kpm.c').read_text()
if 'static int chopin_kpm_copy_string(' in source:
    import runpy
    runpy.run_path(str(Path(__file__).with_name('check_kpm_bridge_copy.py')),run_name='__main__')
    raise SystemExit(0)
start = source.index('} else if (control_code == SUKISU_KPM_VERSION) {')
start += len('} else if (control_code == SUKISU_KPM_VERSION) {')
end = source.index('\n    }\n\nexit:', start)
body = source[start:end]
assert 'strnlen(s->buffer, sizeof(s->buffer))' in body
assert 'outlen > sizeof(s->buffer)' not in body
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __user
static int backend_mode, copy_fault;
static size_t copy_capacity, copied;
static void sukisu_kpm_version(char *out, size_t capacity) {
    memset(out, 0, capacity);
    if (backend_mode == 1) return;
    if (backend_mode == 2) { memset(out, 'X', capacity); return; }
    snprintf(out, capacity, "0.13.9 (probe)");
}
static size_t copy_to_user(void *to, const void *from, size_t length) {
    assert(length <= copy_capacity);
    copied = length;
    if (copy_fault) return length;
    memcpy(to, from, length);
    return 0;
}
static int real_version_branch(unsigned long arg1, unsigned long arg2) {
    struct { char buffer[256]; } storage, *s = &storage;
    int res = 0;
'''
suffix = r'''
exit:
    return res;
}
int main(void) {
    static const unsigned caps[] = {0, 1, 4, 256, 1024};
    unsigned char out[1040];
    unsigned i;
    for (i = 0; i < sizeof(caps)/sizeof(caps[0]); ++i) {
        unsigned cap = caps[i];
        size_t expected = cap ? (cap < 15 ? cap : 15) : 0;
        memset(out, 0xa5, sizeof(out));
        copy_capacity = cap; copied = 0;
        assert(real_version_branch((unsigned long)out, cap) == (cap ? 0 : -EINVAL));
        assert(copied == expected);
        if (cap) {
            assert(out[expected - 1] == 0);
            assert(!memcmp(out, "0.13.9 (probe)", expected - 1));
        }
        assert(out[expected] == 0xa5);
    }
    assert(real_version_branch(0, 256) == -EINVAL);
    copy_capacity = 1024;
    backend_mode = 1;
    assert(real_version_branch((unsigned long)out, 1024) == -ENODEV);
    backend_mode = 2;
    assert(real_version_branch((unsigned long)out, 1024) == -ENODEV);
    backend_mode = 0; copy_fault = 1;
    assert(real_version_branch((unsigned long)out, 1024) == -EFAULT);
    puts("actual VERSION branch: capacities 0/1/4/256/1024, NULL, empty, nonterminated, copy fault PASS");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='chopin-kpm-copy-') as tmp:
    c = Path(tmp) / 'check.c'
    exe = Path(tmp) / 'check'
    c.write_text(prefix + body + suffix)
    subprocess.run(['gcc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
out = Path(os.environ['GITHUB_WORKSPACE']) / 'release-evidence/kpm-version-copy-source.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'status': 'PASS', 'cases': 9,
    'scope': 'actual source branch, bounded simulated userspace/backend; not hardware'}, indent=2))

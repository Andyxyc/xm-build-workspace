"""Execute the actual transformed C path predicate, including UID rejection."""
from pathlib import Path
import re,subprocess,sys,tempfile
s=Path(sys.argv[1]).read_text()
body=re.search(r'static inline long is_exec_adbd\(const char \*filename\)\n\{.*?\n\}',s,re.S)
assert body
source='''#include <string.h>
#include <assert.h>
static unsigned uid_value;
struct uid_value_type { unsigned val; };
static struct uid_value_type current_uid(void) {
    struct uid_value_type u = { uid_value }; return u;
}
'''+body.group()+'''
int main(void) {
    uid_value = 0;
    assert(is_exec_adbd("/system/bin/adbd"));
    assert(is_exec_adbd("/apex/com.android.adbd/bin/adbd"));
    assert(is_exec_adbd("/apex/com.android.adbd@330000000/bin/adbd"));
    assert(!is_exec_adbd("/apex/com.android.adbd.evil/bin/adbd"));
    assert(!is_exec_adbd("/apex/com.android.adbd/bin/adbd-evil"));
    assert(!is_exec_adbd("/apex/evil/bin/adbd"));
    uid_value = 10263;
    assert(!is_exec_adbd("/system/bin/adbd"));
    assert(!is_exec_adbd("/apex/com.android.adbd/bin/adbd"));
    return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'predicate.c').write_text(source)
 subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(p/'predicate.c'),'-o',str(p/'predicate')],check=True)
 subprocess.run([str(p/'predicate')],check=True)
print('PASS: actual ADB-root C predicate: canonical/versioned paths, false prefixes/suffixes and unprivileged callers')

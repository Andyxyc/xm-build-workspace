"""Run the actual transformed SUSFS stat/access C handlers on allowed/denied UIDs."""
from pathlib import Path
import re,subprocess,sys,tempfile
s=Path(sys.argv[1]).read_text();bodies=[]
for name in ['ksu_handle_faccessat','ksu_handle_stat']:
 m=re.search(r'int '+name+r'\([^;]*?\)\s*\{.*?\n\}',s,re.S);assert m,name;bodies.append(m.group())
source='''#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define likely(x) (x)
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define IS_ERR(x) ((long)(x) == -1)
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
static const char su_path[]="/system/bin/su";
static const char sh_path[]="/system/bin/sh";
static bool ksu_su_compat_enabled=true,allowed,chrooted;
struct filename { const char *name; };
struct kuid { unsigned val; };
static struct kuid current_uid(void) { struct kuid u={10263};return u; }
static bool __ksu_is_allow_uid_for_current(unsigned uid) { assert(uid==10263);return allowed; }
static bool current_chrooted(void) {return chrooted;}
'''+ '\n'.join(bodies)+'''
static void check_case(bool grant,bool enabled,bool jailed,const char *expected) {
 char path[64];struct filename f,*p=&f;int dfd=-100,mode=0,flags=0;
 allowed=grant;ksu_su_compat_enabled=enabled;chrooted=jailed;
 strcpy(path,su_path);f.name=path;
 assert(!ksu_handle_faccessat(&dfd,&p,&mode,&flags));assert(!strcmp(path,expected));
 strcpy(path,su_path);
 assert(!ksu_handle_stat(&dfd,&p,&flags));assert(!strcmp(path,expected));
 strcpy(path,"/system/bin/ordinary");
 assert(!ksu_handle_stat(&dfd,&p,&flags));assert(!strcmp(path,"/system/bin/ordinary"));
}
int main(void) {
 check_case(false,true,false,su_path);
 check_case(true,true,false,sh_path);
 check_case(true,false,false,su_path);
 check_case(true,true,true,su_path);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS: actual stat/access C handlers preserve non-root visibility, authorized su, disabled toggle and chroot rejection')

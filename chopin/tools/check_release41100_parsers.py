"""Source-bound parser regression cases; Linux host C mocks, never a device test.

Use the actual guarded parser after update_ci41100.py, the exact old builtin
parser for negative controls, and the unchanged actual4.14 services parser and
QuerySnapshot selector. Policy symbols, MLS backend, SID allocation and locks
are controlled mocks. This does not test live SELinux permission enforcement.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,tempfile

def function(source,name,prefix='static int '):
    matches=list(re.finditer(r'^'+re.escape(prefix+name)+r'\([^;]*?\)\n\{',source,re.M))
    assert len(matches)==1,(name,'expected actual definition rather than prototype')
    a=matches[0].start();b=source.index('\n}',a)+3
    return source[a:b]

PREFIX=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef int gfp_t;
#define SECSID_NULL 0
#define SECINITSID_KERNEL 1
#define SECINITSID_NUM 3
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
struct user_datum { u32 value; };
struct role_datum { u32 value; };
struct type_datum { u32 value;bool attribute; };
struct symtab { void *table;const char *name;void *datum; };
struct policydb {
    struct symtab p_users,p_roles,p_types;
    struct user_datum user;
    struct role_datum role;
    struct type_datum type;
    bool allow_context,require_mls;
    int mls_error,mls_calls;
};
struct context { u32 user,role,type,len;char *str;bool mls_ok; };
struct sidtab { unsigned calls;u32 base;int failure,stale_count;bool reload; };
struct selinux_policy { struct policydb policydb;struct sidtab *sidtab; };
struct selinux_ss { struct policydb policydb;struct sidtab *sidtab;int policy_rwlock; };
struct selinux_state { bool initialized,enforcing;struct selinux_ss *ss;struct selinux_policy *policy; };
static struct selinux_state selinux_state;
static struct selinux_policy *next_live_policy;
/* The tested selector uses only state, not allocation/layout of the full object. */
struct chopin_original_policy { struct selinux_state state; };
static struct chopin_original_policy *chopin_original_policy;
static bool chopin_selinux_hide_enabled=true,current_is_ksu;
static u32 current_uid_value=10001;
struct mock_kuid { u32 val; };
static struct mock_kuid current_uid(void) { return (struct mock_kuid){current_uid_value}; }
static bool susfs_is_current_ksu_domain(void) { return current_is_ksu; }
static bool enforcing_enabled(struct selinux_state *s) { return s->enforcing; }
static const char *initial_sid_to_string[SECINITSID_NUM]={"","kernel","security"};
static unsigned initialized_contexts,destroyed_contexts,live_allocations;
static int alloc_fault,rcu_depth;
static void context_init(struct context *c) { memset(c,0,sizeof(*c));initialized_contexts++; }
static void kfree(void *p) { if(p){assert(live_allocations);live_allocations--;free(p);} }
static void context_destroy(struct context *c) { destroyed_contexts++;kfree(c->str);memset(c,0,sizeof(*c)); }
static void *kmemdup_nul(const void *src,size_t size,gfp_t gfp) {
    (void)gfp;if(alloc_fault || !src)return NULL;
    char *p=malloc(size+1);assert(p);memcpy(p,src,size);p[size]=0;live_allocations++;return p;
}
static char *kstrdup(const char *s,gfp_t gfp) { return kmemdup_nul(s,strlen(s),gfp); }
static void *symtab_search(struct symtab *s,const char *name) {
    return s->name && !strcmp(s->name,name)?s->datum:NULL;
}
static void *hashtab_search(void *s,const char *name) { return symtab_search(s,name); }
static int mls_context_to_sid(struct policydb *p,char delimiter,char *suffix,struct context *c,struct sidtab *tab,u32 def_sid) {
    (void)tab;(void)def_sid;p->mls_calls++;
    if(p->mls_error)return p->mls_error;
    if(!delimiter){c->mls_ok=!p->require_mls;return c->mls_ok?0:-EINVAL;}
    if(strcmp(suffix,"s0:c1,c2"))return -EINVAL;
    c->mls_ok=true;
    /* Deliberately mutate the suffix like the real MLS tokenizer does. */
    char *colon=strchr(suffix,':');assert(colon);*colon=0;
    return 0;
}
static bool policydb_context_isvalid(struct policydb *p,struct context *c) {
    return p->allow_context && c->user==p->user.value && c->role==p->role.value &&
           c->type==p->type.value && (!p->require_mls || c->mls_ok);
}
static void rcu_read_lock(void) { assert(!rcu_depth);rcu_depth=1; }
static void rcu_read_unlock(void) { assert(rcu_depth==1);rcu_depth=0; }
#define rcu_dereference(p) (p)
static void read_lock(int *p) { assert(!*p);*p=1; }
static void read_unlock(int *p) { assert(*p==1);*p=0; }
static int sidtab_context_to_sid(struct sidtab *s,struct context *c,u32 *sid) {
    s->calls++;
    if(s->failure)return s->failure;
    if(s->stale_count){s->stale_count--;if(s->reload)selinux_state.policy=next_live_policy;return -ESTALE;}
    *sid=s->base+c->type;return 0;
}
static int context_struct_to_sid(struct selinux_state *s,struct context *c,u32 *sid) {
    return sidtab_context_to_sid(s->ss->sidtab,c,sid);
}
static void init_policy(struct policydb *p,u32 user,u32 role,u32 type) {
    memset(p,0,sizeof(*p));p->allow_context=true;p->require_mls=true;
    p->user.value=user;p->role.value=role;p->type.value=type;
    p->p_users=(struct symtab){.name="u",.datum=&p->user};p->p_users.table=&p->p_users;
    p->p_roles=(struct symtab){.name="r",.datum=&p->role};p->p_roles.table=&p->p_roles;
    p->p_types=(struct symtab){.name="t",.datum=&p->type};p->p_types.table=&p->p_types;
}
'''

TESTS=r'''
static unsigned checks;
#define CHECK(expr) do { checks++;assert(expr); } while(0)
static const char source[]="u:r:t:s0:c1,c2";
static struct selinux_policy backup,live,reloaded;
static struct sidtab bt,lt,rt;
static void reset_policies(void) {
    CHECK(live_allocations==0 && rcu_depth==0);
    initialized_contexts=destroyed_contexts=0;alloc_fault=0;
    bt=(struct sidtab){.base=100};lt=(struct sidtab){.base=200};rt=(struct sidtab){.base=300};
    init_policy(&backup.policydb,11,12,13);backup.sidtab=&bt;
    init_policy(&live.policydb,1,2,3);live.sidtab=&lt;
    init_policy(&reloaded.policydb,21,22,23);reloaded.sidtab=&rt;
    selinux_state.policy=&live;next_live_policy=&reloaded;
}
static int fixed_parse(const char *input,int *orig) {
    char copy[128];size_t size=strlen(input);assert(size<sizeof(copy));memcpy(copy,input,size+1);
    struct context c,o;int result=release41100_string_to_context_struct(&backup.policydb,&live.policydb,&bt,&lt,copy,input,size,&c,&o,0,orig);
    if(!result)context_destroy(&c);
    if(!result && !*orig)context_destroy(&o);
    return result;
}
static int old_parse(const char *input,int *orig) {
    char left[128],right[128];size_t size=strlen(input);assert(size<sizeof(left));memcpy(left,input,size+1);memcpy(right,input,size+1);
    struct context c,o;int result=builtin_old_string_to_context_struct(&backup.policydb,&live.policydb,&bt,&lt,left,right,&c,&o,0,orig);
    if(!result)context_destroy(&c);
    if(!result && !*orig)context_destroy(&o);
    return result;
}
int main(void) {
    int orig;u32 sid,orig_sid;
    /* Regression control: old code validates backup IDs against live policy. */
    reset_policies();orig=99;CHECK(old_parse(source,&orig)==0 && orig==-EINVAL);
    reset_policies();orig=99;CHECK(fixed_parse(source,&orig)==0 && orig==0);
    CHECK(backup.policydb.mls_calls==1 && live.policydb.mls_calls==1);
    CHECK(initialized_contexts==2 && destroyed_contexts==2);
    CHECK(!strcmp(source,"u:r:t:s0:c1,c2"));
    /* Missing/attribute live symbols must not be accepted by backup IDs. */
    reset_policies();init_policy(&backup.policydb,1,2,3);live.policydb.p_users.datum=NULL;
    orig=99;CHECK(old_parse(source,&orig)==0 && orig==0); /* original false-positive */
    reset_policies();init_policy(&backup.policydb,1,2,3);live.policydb.p_users.datum=NULL;
    orig=99;CHECK(fixed_parse(source,&orig)==0 && orig==-EINVAL);CHECK(live.policydb.mls_calls==0);
    reset_policies();live.policydb.p_roles.datum=NULL;CHECK(fixed_parse(source,&orig)==0 && orig==-EINVAL);
    reset_policies();live.policydb.type.attribute=true;CHECK(fixed_parse(source,&orig)==0 && orig==-EINVAL);
    reset_policies();backup.policydb.p_users.datum=NULL;CHECK(fixed_parse(source,&orig)==-EINVAL && orig==-EINVAL);CHECK(destroyed_contexts==2);
    reset_policies();backup.policydb.type.attribute=true;CHECK(fixed_parse(source,&orig)==-EINVAL && orig==-EINVAL);
    reset_policies();backup.policydb.mls_error=-ERANGE;CHECK(fixed_parse(source,&orig)==-ERANGE && orig==-EINVAL);CHECK(destroyed_contexts==2);
    /* Original bug: a failed backup may leave a successful live context alive. */
    reset_policies();init_policy(&backup.policydb,1,2,3);backup.policydb.allow_context=false;
    CHECK(old_parse(source,&orig)==-EINVAL && orig==0);CHECK(destroyed_contexts==1);
    reset_policies();init_policy(&backup.policydb,1,2,3);backup.policydb.allow_context=false;
    CHECK(fixed_parse(source,&orig)==-EINVAL && orig==-EINVAL);CHECK(destroyed_contexts==2);
    const char *invalid[]={"","u","u:r","u:r:absent:s0:c1,c2","u:r:t:s1","u:r:t"};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        reset_policies();CHECK(fixed_parse(invalid[i],&orig)==-EINVAL);CHECK(orig==-EINVAL && destroyed_contexts==2);
    }

    /* Actual new wrapper: preserve input, valid SID assignment, one allocation. */
    reset_policies();sid=orig_sid=99;orig=99;
    CHECK(release41100_security_context_to_sid_with_policy(&backup,source,strlen(source),&sid,0,0,&orig_sid,&orig)==0);
    CHECK(sid==113 && orig_sid==203 && orig==0);CHECK(live_allocations==0 && rcu_depth==0);
    CHECK(initialized_contexts==2 && destroyed_contexts==2 && !strcmp(source,"u:r:t:s0:c1,c2"));
    reset_policies();lt.stale_count=1;lt.reload=true;sid=orig_sid=99;
    CHECK(release41100_security_context_to_sid_with_policy(&backup,source,strlen(source),&sid,0,0,&orig_sid,&orig)==0);
    CHECK(sid==113 && orig_sid==323 && orig==0);CHECK(bt.calls==2 && lt.calls==1 && rt.calls==1);
    CHECK(live_allocations==0 && rcu_depth==0 && destroyed_contexts==4);
    CHECK(!strcmp(source,"u:r:t:s0:c1,c2"));
    reset_policies();lt.failure=-EIO;orig_sid=99;
    CHECK(release41100_security_context_to_sid_with_policy(&backup,source,strlen(source),&sid,0,0,&orig_sid,&orig)==0);
    CHECK(orig==-EIO && orig_sid==0 && sid==113);CHECK(live_allocations==0 && destroyed_contexts==2);
    reset_policies();bt.failure=-ENOSPC;orig_sid=99;
    CHECK(release41100_security_context_to_sid_with_policy(&backup,source,strlen(source),&sid,0,0,&orig_sid,&orig)==-ENOSPC);
    CHECK(orig==-ENOSPC && lt.calls==0 && orig_sid==0);CHECK(live_allocations==0 && destroyed_contexts==2);
    reset_policies();alloc_fault=1;
    CHECK(release41100_security_context_to_sid_with_policy(&backup,source,strlen(source),&sid,0,0,&orig_sid,&orig)==-ENOMEM);
    CHECK(initialized_contexts==0 && live_allocations==0);
    reset_policies();CHECK(release41100_security_context_to_sid_with_policy(&backup,"",0,&sid,0,0,&orig_sid,&orig)==-EINVAL);
    CHECK(live_allocations==0 && initialized_contexts==0);

    /* Active4.14 code: each selected state gets its own untouched input copy. */
    struct selinux_ss ss_backup={0},ss_live={0};struct sidtab native_bt={.base=400},native_lt={.base=500};
    init_policy(&ss_backup.policydb,11,12,13);ss_backup.sidtab=&native_bt;
    init_policy(&ss_live.policydb,1,2,3);ss_live.sidtab=&native_lt;
    struct chopin_original_policy snapshot={.state={.initialized=true,.enforcing=true,.ss=&ss_backup}};
    selinux_state=(struct selinux_state){.initialized=true,.enforcing=true,.ss=&ss_live};
    chopin_original_policy=&snapshot;chopin_selinux_hide_enabled=true;current_uid_value=10001;current_is_ksu=false;
    struct selinux_state *selected=chopin_selinux_query_state(&selinux_state);
    CHECK(selected==&snapshot.state);
    CHECK(native414_security_context_to_sid_core(selected,source,strlen(source),&sid,0,0,0)==0 && sid==413);
    CHECK(native414_security_context_to_sid_core(&selinux_state,source,strlen(source),&sid,0,0,0)==0 && sid==503);
    CHECK(!strcmp(source,"u:r:t:s0:c1,c2") && live_allocations==0);
    /* A root-only type exists solely in the live policy. */
    ss_live.policydb.p_types.name="ksu";
    const char root_only[]="u:r:ksu:s0:c1,c2";
    CHECK(native414_security_context_to_sid_core(selected,root_only,strlen(root_only),&sid,0,0,0)==-EINVAL);
    CHECK(native414_security_context_to_sid_core(&selinux_state,root_only,strlen(root_only),&sid,0,0,0)==0);
    CHECK(!strcmp(root_only,"u:r:ksu:s0:c1,c2") && live_allocations==0);
    current_uid_value=2000;CHECK(chopin_selinux_query_state(&selinux_state)==&selinux_state);
    current_uid_value=110001;CHECK(chopin_selinux_query_state(&selinux_state)==&snapshot.state);
    current_is_ksu=true;CHECK(chopin_selinux_query_state(&selinux_state)==&selinux_state);current_is_ksu=false;
    selinux_state.enforcing=false;CHECK(chopin_selinux_query_state(&selinux_state)==&selinux_state);selinux_state.enforcing=true;
    chopin_selinux_hide_enabled=false;CHECK(chopin_selinux_query_state(&selinux_state)==&selinux_state);chopin_selinux_hide_enabled=true;
    chopin_original_policy=NULL;CHECK(chopin_selinux_query_state(&selinux_state)==&selinux_state);
    CHECK(live_allocations==0 && rcu_depth==0 && ss_live.policy_rwlock==0 && ss_backup.policy_rwlock==0);
    printf("{\"checks\":%u,\"old_parser_regressions_reproduced\":3,\"native414_state_backend_unchanged\":true}\n",checks);
    return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel-root',type=Path);p.add_argument('--report',type=Path,default=Path('release41100-parser-tests.json'));p.add_argument('--prepare-only',type=Path);a=p.parse_args()
    root=(a.kernel_root or Path(os.environ['WORKSPACE'])/'android-kernel').resolve();here=Path(__file__).resolve().parent/'susfs230';pin=json.loads((here/'ci41100-source.json').read_text(encoding='utf-8'));up=here/'upstream-ci41100';sha=lambda b:hashlib.sha256(b).hexdigest()
    current=(root/'KernelSU/kernel/feature/selinux_hide.c').read_text(encoding='utf-8');old=(up/'builtin6397/kernel/feature/selinux_hide.c').read_text(encoding='utf-8');native=(root/'security/selinux/ss/services.c').read_text(encoding='utf-8');snapshot=(root/'KernelSU/kernel/chopin_selinux_query_snapshot.c').read_text(encoding='utf-8')
    assert sha(current.encode())==pin['patched_builtin_selinux_hide_sha256']
    assert sha(native.encode())==pin['expected_before_sha256']['security/selinux/ss/services.c']
    assert sha(snapshot.encode())==pin['expected_before_sha256']['KernelSU/kernel/chopin_selinux_query_snapshot.c']
    for name,digest in pin['new_parser_function_sha256'].items():assert sha(function(current,name).encode())==digest
    new_code='\n'.join(function(current,n) for n in ['string_to_context_struct','security_context_to_sid_with_policy'])
    new_code=re.sub(r'\bstring_to_context_struct\b','release41100_string_to_context_struct',new_code)
    new_code=re.sub(r'\bsecurity_context_to_sid_with_policy\b','release41100_security_context_to_sid_with_policy',new_code)
    old_code=function(old,'string_to_context_struct');assert sha(old_code.encode())==pin['old_parser_function_sha256']['string_to_context_struct'];old_code=re.sub(r'\bstring_to_context_struct\b','builtin_old_string_to_context_struct',old_code)
    native_code='\n'.join(function(native,n) for n in ['string_to_context_struct','security_context_to_sid_core'])
    native_code=re.sub(r'\bstring_to_context_struct\b','native414_string_to_context_struct',native_code)
    native_code=re.sub(r'\bsecurity_context_to_sid_core\b','native414_security_context_to_sid_core',native_code)
    selector=function(snapshot,'chopin_selinux_query_state','struct selinux_state *')
    c='\n'.join([PREFIX,new_code,old_code,native_code,selector,TESTS])
    report={'status':'PREPARED_ONLY_NO_C_COMPILE_OR_EXECUTION','source_commit':pin['main_commit'],'guarded_dual_parser_sha256':sha(current.encode()),'active_native_services_sha256':sha(native.encode()),'active_snapshot_sha256':sha(snapshot.encode()),'generated_C_sha256':sha(c.encode()),'tested_source_rewritten_only_to_disambiguate_function_names':True,'actual_backend_data_lookup_MLS_SID_locks_are_mocks':True,'kernel_compiled':False,'phone_accessed':False,'SELinux_enforcement_runtime_verified':False,'case_groups':['old-renumbered-ID-wrong-context-validation-negative-control','old-missing-original-user-false-positive-negative-control','old-failed-backup-cleanup-negative-control','fixed-private-MLS-suffix-restore','fixed-ESTALE-live-policy-reload-and-private-copy-reset','SID-allocation-failure-and-output-init','empty-allocation-and-malformed-contexts','actual-native414-two-state-independent-parser','actual-QuerySnapshot-selector-system-app-root-enforcing-disabled-controls']}
    if a.prepare_only:
        a.prepare_only.mkdir(parents=True,exist_ok=True);(a.prepare_only/'release41100_parser_test.c').write_text(c,encoding='utf-8',newline='\n')
    else:
        with tempfile.TemporaryDirectory(prefix='release41100-parser-') as temp:
            d=Path(temp);f=d/'test.c';exe=d/'test';f.write_text(c,encoding='utf-8',newline='\n')
            q=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Wno-unused-parameter','-Wno-unused-function',str(f),'-o',str(exe)],capture_output=True,text=True,timeout=60);assert q.returncode==0,q.stderr
            q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10);assert q.returncode==0,q.stdout+q.stderr
            counts=json.loads(q.stdout.strip());assert counts['checks']>=70 and counts['old_parser_regressions_reproduced']==3
            report.update(status='PASS_ACTUAL_SOURCE_PARSER_HOST_CASES_ONLY',host_execution=counts)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()

/* SPDX-License-Identifier: GPL-2.0-only */
/* Temporary diagnosis only. No hooks, task writes, policies or persistent state.
 * Pinned ARM64 4.14 has thread_info at task offset0 and flags at offset0.
 * The controller must independently verify those layouts and PREEMPT_RCU.
 */
#include <compiler.h>
#include <kpmodule.h>
#include <linux/string.h>
#include <kallsyms.h>
KPM_NAME("chopin_threadflags_readonly");
KPM_VERSION("1.0.0");
KPM_LICENSE("GPL v2");
KPM_AUTHOR("chopin port validation");
KPM_DESCRIPTION("Read only SUSFS thread flags under RCU; no hooks");
static void *(*find_task)(int pid);
static void (*read_lock)(void);
static void (*read_unlock)(void);
static volatile unsigned int *zygote_sid;
static long start(const char *a,const char *b,void *__user c){
 if(!kallsyms_lookup_name)return -2;
 find_task=(void *)kallsyms_lookup_name("find_task_by_vpid");
 read_lock=(void *)kallsyms_lookup_name("__rcu_read_lock");
 read_unlock=(void *)kallsyms_lookup_name("__rcu_read_unlock");
 zygote_sid=(void *)kallsyms_lookup_name("susfs_zygote_sid");
 return find_task&&read_lock&&read_unlock&&zygote_sid?0:-2;
}
static long control(const char *a,char *__user out,int length){
 unsigned long pid=0,flags=0;void *task;
 if(!a)return -22;
 if(!strcmp(a,"zygote_sid"))return *zygote_sid;
 for(;*a;a++){if(*a<'0'||*a>'9'||pid>214748364UL)return -22;pid=pid*10+(*a-'0');}
 if(!pid||pid>2147483647UL)return -22;
 read_lock();task=find_task((int)pid);
 if(task)flags=*(volatile unsigned long *)task;
 read_unlock();
 return task?(long)((flags>>33)&7):-3;
}
static long stop(void *__user r){return 0;}
KPM_INIT(start);KPM_CTL0(control);KPM_EXIT(stop);

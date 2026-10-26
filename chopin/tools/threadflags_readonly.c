/* SPDX-License-Identifier: GPL-2.0-only */
/* Temporary diagnosis only. No hooks, task writes, policies or persistent state.
 * Pinned ARM64 4.14 has thread_info at task offset0 and flags at offset0.
 * The controller must independently verify those layouts and PREEMPT_RCU.
 */
#include <compiler.h>
#include <kpmodule.h>
#include <linux/string.h>
KPM_NAME("chopin_threadflags_readonly");
KPM_VERSION("1.0.0");
KPM_LICENSE("GPL v2");
KPM_AUTHOR("chopin port validation");
KPM_DESCRIPTION("Read only SUSFS thread flags under RCU; no hooks");
extern void *find_task_by_vpid(int pid);
extern void __rcu_read_lock(void);
extern void __rcu_read_unlock(void);
extern unsigned int susfs_zygote_sid;
static long start(const char *a,const char *b,void *__user c){return 0;}
static long control(const char *a,char *__user out,int length){
 unsigned long pid=0,flags=0;void *task;
 if(!a)return -22;
 if(!strcmp(a,"zygote_sid"))return *(volatile unsigned int *)&susfs_zygote_sid;
 for(;*a;a++){if(*a<'0'||*a>'9'||pid>214748364UL)return -22;pid=pid*10+(*a-'0');}
 if(!pid||pid>2147483647UL)return -22;
 __rcu_read_lock();task=find_task_by_vpid((int)pid);
 if(task)flags=*(volatile unsigned long *)task;
 __rcu_read_unlock();
 return task?(long)((flags>>33)&7):-3;
}
static long stop(void *__user r){return 0;}
KPM_INIT(start);KPM_CTL0(control);KPM_EXIT(stop);

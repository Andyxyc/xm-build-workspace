/* Read-only observations. No hooks, policy changes or persistent process. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/select.h>
#include <sys/resource.h>
#include <sched.h>
#include <signal.h>
#include <grp.h>
#include <sys/prctl.h>
#ifndef CHOPIN_SOCKET_LISTENER
#include <jni.h>
JNIEXPORT jstring JNICALL Java_cn_chopin_acceptanceprobe_NativeProbe_status(JNIEnv *e,jclass c) {
 (void)c;char out[512];int fd=open("/sys/fs/selinux/status",O_RDONLY|O_CLOEXEC);
 if(fd<0){snprintf(out,sizeof(out),"{\"error_errno\":%d,\"stage\":\"open\"}",errno);return (*e)->NewStringUTF(e,out);}
 volatile uint32_t *p=mmap(NULL,20,PROT_READ,MAP_SHARED,fd,0);int err=errno;close(fd);
 if(p==MAP_FAILED){snprintf(out,sizeof(out),"{\"error_errno\":%d,\"stage\":\"mmap\"}",err);return (*e)->NewStringUTF(e,out);}
 uint32_t v[5];int ok=0;for(int i=0;i<100;i++){
  uint32_t s=__atomic_load_n(&p[1],__ATOMIC_ACQUIRE);if(s&1)continue;
  for(int n=0;n<5;n++)v[n]=__atomic_load_n(&p[n],__ATOMIC_ACQUIRE);
  if(s==__atomic_load_n(&p[1],__ATOMIC_ACQUIRE)){ok=1;break;}
 }
 munmap((void*)p,20);
 if(ok)snprintf(out,sizeof(out),"{\"version\":%u,\"sequence\":%u,\"enforcing\":%u,\"policyload\":%u,\"deny_unknown\":%u,\"direct_mmap\":true}",v[0],v[1],v[2],v[3],v[4]);
 else snprintf(out,sizeof(out),"{\"error_errno\":%d,\"stage\":\"seqlock\"}",EBUSY);
 return (*e)->NewStringUTF(e,out);
}
JNIEXPORT jstring JNICALL Java_cn_chopin_acceptanceprobe_NativeProbe_connect(JNIEnv *e,jclass c,jstring path){
 (void)c;const char *s=(*e)->GetStringUTFChars(e,path,NULL);struct sockaddr_un a={.sun_family=AF_UNIX};char out[160];
 int result=-1,err=ENAMETOOLONG,fd=-1;if(strlen(s)<sizeof(a.sun_path)){
  strcpy(a.sun_path,s);fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);
  if(fd>=0){result=connect(fd,(struct sockaddr*)&a,sizeof(a));err=result?errno:0;close(fd);}else err=errno;
 }
 (*e)->ReleaseStringUTFChars(e,path,s);snprintf(out,sizeof(out),"{\"result\":%d,\"errno\":%d,\"local_unix_only\":true}",result,err);return (*e)->NewStringUTF(e,out);
}
JNIEXPORT jstring JNICALL Java_cn_chopin_acceptanceprobe_NativeProbe_priority(JNIEnv *e,jclass c,jint uid){
 (void)c;char out[128];errno=0;int value=getpriority(PRIO_USER,uid),err=errno;
 snprintf(out,sizeof(out),"{\"uid\":%d,\"value\":%d,\"errno\":%d,\"read_only\":true}",uid,value,err);return (*e)->NewStringUTF(e,out);
}
JNIEXPORT jstring JNICALL Java_cn_chopin_acceptanceprobe_NativeProbe_scheduler(JNIEnv *e,jclass c,jint pid){
 (void)c;char out[512];if(pid<=1)return (*e)->NewStringUTF(e,"{\"error\":\"invalid task PID\"}");
 errno=0;int scheduler=sched_getscheduler(pid),se=errno;
 errno=0;int pgid=getpgid(pid),pe=errno;
 errno=0;int session=getsid(pid),ie=errno;
 /* Signal zero checks permission/existence; it does not deliver a signal. */
 errno=0;int signal_zero=kill(pid,0),ze=errno;
 snprintf(out,sizeof(out),"{\"target_pid\":%d,\"result\":%d,\"errno\":%d,\"getpgid_result\":%d,\"getpgid_errno\":%d,\"getsid_result\":%d,\"getsid_errno\":%d,\"signal_zero_result\":%d,\"signal_zero_errno\":%d,\"read_only\":true,\"no_signal_delivered\":true}",pid,scheduler,se,pgid,pe,session,ie,signal_zero,ze);return (*e)->NewStringUTF(e,out);
}
#else
int main(int argc,char **argv){
 if(argc==5 && !strcmp(argv[1],"--query-access")){
  char request[512],response[512];int cls=atoi(argv[4]);if(geteuid()!=0||strlen(argv[2])>150||strlen(argv[3])>150||cls<=0)return 64;
  int n=snprintf(request,sizeof(request),"%s %s %d",argv[2],argv[3],cls);int q=open("/sys/fs/selinux/access",O_RDWR|O_CLOEXEC);
  if(q<0||write(q,request,n)!=n||lseek(q,0,SEEK_SET)<0)return 65;
  int count=read(q,response,sizeof(response)-1);if(count<0)return 66;response[count]=0;puts(response);close(q);return 0;
 }
 const char *prefix="/data/user/0/cn.chopin.acceptanceprobe3/files/chopin-avc-";
 if((argc!=2&&argc!=3)||strncmp(argv[1],prefix,strlen(prefix)))return 2;
 struct sockaddr_un a={.sun_family=AF_UNIX};struct stat initial,owned,current;
 if(strlen(argv[1])>=sizeof(a.sun_path)||lstat(argv[1],&initial)==0||errno!=ENOENT)return 3;
 strcpy(a.sun_path,argv[1]);int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);if(fd<0)return 4;
 if(bind(fd,(struct sockaddr*)&a,sizeof(a))||lstat(argv[1],&owned)||chmod(argv[1],0666)||listen(fd,1))return 5;
 if(argc==3){
  char *end=NULL;unsigned long uid=strtoul(argv[2],&end,10);if(!end||*end||uid<10000||uid>1999999999UL)return 6;
  if(setgroups(0,NULL)||setresgid(uid,uid,uid)||setresuid(uid,uid,uid)||prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0))return 7;
 }
 char context[256]={0};int cf=open("/proc/self/attr/current",O_RDONLY);if(cf>=0){read(cf,context,sizeof(context)-1);close(cf);}context[strcspn(context,"\n")]=0;
 printf("{\"ready\":true,\"pid\":%d,\"uid\":%d,\"context\":\"%s\",\"timeout_seconds\":15}\n",getpid(),getuid(),context);fflush(stdout);
 fd_set set;FD_ZERO(&set);FD_SET(fd,&set);struct timeval wait={15,0};int ready=select(fd+1,&set,NULL,NULL,&wait);
 if(ready>0){int client=accept4(fd,NULL,NULL,SOCK_CLOEXEC);if(client>=0){close(client);puts("{\"accepted\":true}");}}
 close(fd);if(!lstat(argv[1],&current)&&current.st_ino==owned.st_ino&&current.st_dev==owned.st_dev)unlink(argv[1]);return 0;
}
#endif

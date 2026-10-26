/* SPDX-License-Identifier: GPL-2.0-only */
/* Finite, read-only multicast audit observation; never AUDIT_SET or policy IO. */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/audit.h>
#include <linux/netlink.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static long long milliseconds(void) {
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;
 return (long long)t.tv_sec*1000+t.tv_nsec/1000000;
}
static void string(const unsigned char *s,size_t n) {
 putchar('"');for(size_t i=0;i<n;i++) {
  unsigned char c=s[i];if(c=='"'||c=='\\'){putchar('\\');putchar(c);}
  else if(c>=32&&c<127)putchar(c);else printf("\\u%04x",c);
 }putchar('"');
}
int main(int argc,char **argv) {
 if(argc!=2)return 64;char *end;long seconds=strtol(argv[1],&end,10);
 if(*end||seconds<2||seconds>15||geteuid()!=0)return 64;
 int fd=socket(AF_NETLINK,SOCK_RAW|SOCK_CLOEXEC,NETLINK_AUDIT);
 if(fd<0){printf("{\"ready\":false,\"stage\":\"socket\",\"errno\":%d}\n",errno);return 65;}
 struct sockaddr_nl address={.nl_family=AF_NETLINK,.nl_pid=0,.nl_groups=1};
 if(bind(fd,(struct sockaddr*)&address,sizeof(address))){printf("{\"ready\":false,\"stage\":\"bind-readlog-group\",\"errno\":%d}\n",errno);close(fd);return 66;}
 printf("{\"ready\":true,\"read_only\":true,\"pid\":%d,\"group\":1,\"timeout_seconds\":%ld}\n",getpid(),seconds);fflush(stdout);
 unsigned char buffer[65536];long long limit=milliseconds()+seconds*1000;unsigned long total=0,matches=0;
 while(milliseconds()<limit) {
  struct pollfd request={.fd=fd,.events=POLLIN};int wait=(int)(limit-milliseconds());if(wait<=0)break;
  if(poll(&request,1,wait)<0){if(errno==EINTR)continue;break;}
  if(!(request.revents&POLLIN))continue;
  ssize_t count=recv(fd,buffer,sizeof(buffer),MSG_DONTWAIT);if(count<0){if(errno==EAGAIN||errno==EINTR)continue;break;}
  int remaining=(int)count;
  for(struct nlmsghdr *h=(void*)buffer;NLMSG_OK(h,remaining);h=NLMSG_NEXT(h,remaining)) {
   total++;size_t bytes=h->nlmsg_len-NLMSG_HDRLEN;unsigned char *text=NLMSG_DATA(h);
   if(h->nlmsg_type==AUDIT_AVC&&memmem(text,bytes,"getsched",sizeof("getsched")-1)&&memmem(text,bytes,"cceptanceprobe3",sizeof("cceptanceprobe3")-1)) {
    printf("{\"audit_type\":%u,\"raw_kernel_audit\":",h->nlmsg_type);string(text,bytes);puts("}");fflush(stdout);matches++;
   }
  }
 }
 close(fd);printf("{\"finished\":true,\"messages_observed\":%lu,\"matching_owned_probe_denials\":%lu,\"policy_writes\":0}\n",total,matches);return 0;
}

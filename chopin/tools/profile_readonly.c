/* SPDX-License-Identifier: GPL-2.0-only */
/* Read-only runtime profile diagnosis; no root grants or profile changes. */
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"
int main(int argc,char **argv) {
 if(argc!=3 || geteuid()!=0 || strlen(argv[2])>=KSU_MAX_PACKAGE_NAME)return 2;
 char *end=NULL;unsigned long uid=strtoul(argv[1],&end,10);if(!end||*end||uid>2147483647UL)return 2;
 int fd=-1;long s=syscall(SYS_reboot,KSU_INSTALL_MAGIC1,KSU_INSTALL_MAGIC2,0,&fd);
 if(s<0||fd<0){perror("driver fd");return 1;}
 struct ksu_uid_granted_root_cmd grant={.uid=uid};
 struct ksu_uid_should_umount_cmd umount={.uid=uid};
 struct ksu_get_app_profile_cmd app={0};app.profile.version=KSU_APP_PROFILE_VER;app.profile.curr_uid=uid;strcpy(app.profile.key,argv[2]);
 int a=ioctl(fd,KSU_IOCTL_UID_GRANTED_ROOT,&grant);int ae=a<0?errno:0;
 int b=ioctl(fd,KSU_IOCTL_UID_SHOULD_UMOUNT,&umount);int be=b<0?errno:0;
 int p=ioctl(fd,KSU_IOCTL_GET_APP_PROFILE,&app);int pe=p<0?errno:0;
 printf("{\"root_query\":%d,\"root_errno\":%d,\"granted_root\":%u,\"umount_query\":%d,\"umount_errno\":%d,\"should_umount\":%u,\"profile_query\":%d,\"profile_errno\":%d,\"profile_bytes\":%zu,\"profile_version\":%u,\"allow_su\":%u,\"nonroot_use_default\":%u,\"nonroot_umount\":%u}\n",a,ae,grant.granted,b,be,umount.should_umount,p,pe,sizeof(app.profile),app.profile.version,app.profile.allow_su,app.profile.nrp_config.use_default,app.profile.nrp_config.profile.umount_modules);
 close(fd);return a<0||b<0;
}

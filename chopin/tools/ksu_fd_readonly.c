/* SPDX-License-Identifier: GPL-2.0-only */
/* Read-only driver transport probe: no root grant, module load or real reboot. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"
int main(void)
{
    int fd=-1,err;
    struct ksu_get_info_cmd info={0};
    char path[80],name[160]={0};
    printf("uid=%u euid=%u magic1=%08x magic2=%08x\n",getuid(),geteuid(),KSU_INSTALL_MAGIC1,KSU_INSTALL_MAGIC2);
    /* These are NOT Linux's reboot magic values; command 0 is not a reboot op. */
    errno=0;
    long rc=syscall(SYS_reboot,KSU_INSTALL_MAGIC1,KSU_INSTALL_MAGIC2,0,&fd);
    err=errno;
    printf("install_fd syscall=%ld errno=%d fd=%d\n",rc,err,fd);
    if (fd<0) { (void)syscall(SYS_getpid); printf("after_safe_getpid fd=%d\n",fd); }
    if (fd<0) return 3;
    snprintf(path,sizeof(path),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(path,name,sizeof(name)-1);
    printf("fd_name=%s readlink=%zd errno=%d\n",name,n,n<0?errno:0);
    errno=0;rc=ioctl(fd,KSU_IOCTL_GET_INFO,&info);err=errno;
    printf("get_info ioctl=%ld errno=%d version=%u flags=%u features=%u uapi=%u\n",rc,err,info.version,info.flags,info.features,info.uapi_version);
    if (rc<0) {
        struct ksu_get_info_legacy_cmd legacy={0};
        errno=0;rc=ioctl(fd,KSU_IOCTL_GET_INFO_LEGACY,&legacy);err=errno;
        printf("legacy_get_info ioctl=%ld errno=%d version=%u flags=%u features=%u\n",rc,err,legacy.version,legacy.flags,legacy.features);
    }
    close(fd);
    return rc<0?4:0;
}

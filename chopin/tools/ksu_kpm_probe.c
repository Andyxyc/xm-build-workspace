/* SPDX-License-Identifier: GPL-2.0-only */
/* Uses the pinned SukiSU UAPI. Default operation only reads information. */
#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"
#include "uapi/extension.h"

_Static_assert(sizeof(struct ksu_extension_cmd) == 32, "extension UAPI layout");
_Static_assert(sizeof(struct ksu_kpm_cmd) == 32, "KPM UAPI layout");
static int kpm(int fd, unsigned op, const void *a, uintptr_t b)
{
    int result = -EINPROGRESS;
    struct ksu_kpm_cmd cmd = {op, (uintptr_t)a, b, (uintptr_t)&result};
    struct ksu_extension_cmd ext = {
        .id=KSU_EXTENSION_KPM, .op=KSU_EXTENSION_IO, .user_ptr=(uintptr_t)&cmd
    };
    if (ioctl(fd, KSU_IOCTL_EXTENSION, &ext) < 0)
        return -errno;
    return result;
}
int main(int argc, char **argv)
{
    int fd=-1, status=1, loaded=0, before=-1;
    const char name[]="chopin_kpm_probe";
    char buffer[1024]={0}, resolved[PATH_MAX];
    struct ksu_get_info_cmd info={0};
    struct ksu_extension_cmd extension={.id=KSU_EXTENSION_KPM,.op=KSU_EXTENSION_GET};
    if (argc!=1 && !(argc==3 && !strcmp(argv[1],"lifecycle"))) {
        fprintf(stderr,"usage: %s [lifecycle /absolute/path/chopin_kpm_probe.kpm]\n",argv[0]);
        return 2;
    }
    if (geteuid()!=0) {fputs("root required\n",stderr);return 1;}
    /* Both magic values differ from Android's reboot command pair. */
    long installed=syscall(SYS_reboot,KSU_INSTALL_MAGIC1,KSU_INSTALL_MAGIC2,0,&fd);
    if (installed<0 || fd<0) {
        fprintf(stderr,"KSU fd unavailable: syscall=%ld errno=%d fd=%d\n",installed,errno,fd);
        return 1;
    }
    if (ioctl(fd,KSU_IOCTL_GET_INFO,&info)<0 || info.uapi_version!=KERNEL_SU_UAPI_VERSION) {
        fputs("matching SukiSU UAPI unavailable\n",stderr);goto done;
    }
    printf("KSU version=%u uapi=%u flags=%u\n",info.version,info.uapi_version,info.flags);
    if (ioctl(fd,KSU_IOCTL_EXTENSION,&extension)<0 || !(extension.supported&KSU_FEATURE_FLAG_SUPPORTED) || !extension.value) {
        fputs("KPM extension unavailable\n",stderr);goto done;
    }
    /* The current legacy driver bounds VERSION by its 256-byte scratch string. */
    int rc=kpm(fd,SUKISU_KPM_VERSION,buffer,256);
    if (rc<0) {fprintf(stderr,"KPM version error=%d\n",rc);goto done;}
    printf("KPM version=%.*s\n",(int)sizeof(buffer),buffer);
    before=kpm(fd,SUKISU_KPM_NUM,NULL,0);
    if (before<0) {fprintf(stderr,"KPM count error=%d\n",before);goto done;}
    printf("KPM count=%d\n",before);
    memset(buffer,0,sizeof(buffer));
    rc=kpm(fd,SUKISU_KPM_LIST,buffer,sizeof(buffer));
    if (rc<0) {fprintf(stderr,"KPM list error=%d\n",rc);goto done;}
    printf("KPM list=%.*s\n",(int)sizeof(buffer),buffer);
    if (argc==1) {status=0;goto done;}
    if (strstr(buffer,name)) {fputs("probe already loaded; preserving existing state\n",stderr);goto done;}
    if (argv[2][0]!='/' || !realpath(argv[2],resolved) || strcmp(strrchr(resolved,'/')+1,"chopin_kpm_probe.kpm")) {
        fputs("exact probe module path required\n",stderr);goto done;
    }
    struct stat st;
    if (stat(resolved,&st) || !S_ISREG(st.st_mode) || st.st_size!=3104) {
        fputs("audited probe file size/type mismatch\n",stderr);goto done;
    }
    rc=kpm(fd,SUKISU_KPM_LOAD,resolved,0);
    printf("KPM load result=%d\n",rc);
    if (rc) goto done;
    loaded=1;
    if (kpm(fd,SUKISU_KPM_NUM,NULL,0)!=before+1) goto done;
    memset(buffer,0,sizeof(buffer));
    if (kpm(fd,SUKISU_KPM_INFO,name,(uintptr_t)buffer)<0 || !strstr(buffer,name)) goto done;
    rc=kpm(fd,SUKISU_KPM_CONTROL,name,(uintptr_t)"ping");
    printf("KPM control result=%d expected=%d\n",rc,0x1357);
    if (rc!=0x1357) goto done;
    status=0;
done:
    if (loaded) {
        int rc=kpm(fd,SUKISU_KPM_UNLOAD,name,0);
        int after=kpm(fd,SUKISU_KPM_NUM,NULL,0);
        printf("KPM unload result=%d final_count=%d expected_count=%d\n",rc,after,before);
        if (rc || after!=before) status=1;
    }
    if (fd>=0) close(fd);
    return status;
}

/* Read-only MediaTek UFS descriptor probe. No write/query-set/FFU/RPMB path. */
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <scsi/sg.h>
struct query { uint32_t opcode; uint8_t idn,idx; uint16_t size; void *ptr; };
_Static_assert(sizeof(struct query)==16,"MTK ARM64 query layout");
struct feature { uint32_t opcode; uint8_t idn,pad; uint16_t size; uint8_t reserved[8],data[256]; };
_Static_assert(offsetof(struct feature,data)==16,"MTK feature output offset");
int main(int argc,char **argv) {
 if(argc!=2 || strcmp(argv[1],"/dev/block/sdc")) { fputs("Expected audited chopin UFS LUN /dev/block/sdc\n",stderr);return 64; }
 int fd=open(argv[1],O_RDONLY|O_CLOEXEC|O_NONBLOCK); if(fd<0){perror("open UFS read-only");return 1;}
 struct stat st; if(fstat(fd,&st)||!S_ISBLK(st.st_mode)){close(fd);return 65;}
 unsigned boot=0;struct query q={.opcode=3,.idn=0,.size=4,.ptr=&boot};
 int r=ioctl(fd,0x5388,&q);printf("boot_lun_query_rc=%d errno=%d boot_lun=%u\n",r,r?errno:0,boot);
 struct feature f={.opcode=0x55000001,.idn=2,.size=64};
 r=ioctl(fd,0x5388,&f);printf("unit_descriptor_rc=%d errno=%d\n",r,r?errno:0);
 if(!r && f.data[0]>=6 && f.data[1]==2) printf("unit_write_protect=%u boot_lun_id=%u unit_index=%u\n",f.data[5],f.data[4],f.data[2]);
 unsigned char data[64]={0},sense[64]={0},cdb[6]={0x1a,0,0x3f,0,64,0};
 sg_io_hdr_t h={.interface_id='S',.dxfer_direction=SG_DXFER_FROM_DEV,.cmd_len=6,.mx_sb_len=64,.dxfer_len=64,.dxferp=data,.cmdp=cdb,.sbp=sense,.timeout=3000};
 r=ioctl(fd,SG_IO,&h);printf("mode_sense_rc=%d errno=%d scsi_status=%u host=%u driver=%u\n",r,r?errno:0,h.status,h.host_status,h.driver_status);
 if(!r && !h.status && !h.host_status && !h.driver_status) printf("lun_mode_write_protect=%u\n",!!(data[2]&0x80));
 puts("scope=read_queries_only; zero write protection does not prove individual ranges writable");
 close(fd);return 0;
}

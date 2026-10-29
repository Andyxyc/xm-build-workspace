/* Read-only MediaTek UFS queries. No write/query-set/FFU/RPMB path. */
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

static void report_sense(const unsigned char *sense,unsigned count)
{
 unsigned length=count>64U?64U:count;
 printf("sense_raw=");
 for(unsigned i=0;i<length;i++) printf("%02x",(unsigned)sense[i]);
 putchar('\n');
 if(length>=14U && (sense[0]&0x7fU)>=0x70U && (sense[0]&0x7fU)<=0x71U && sense[7]>=6U)
  printf("sense_key=0x%02x asc=0x%02x ascq=0x%02x format=fixed\n",(unsigned)(sense[2]&0x0fU),(unsigned)sense[12],(unsigned)sense[13]);
 else if(length>=4U && (sense[0]&0x7fU)>=0x72U && (sense[0]&0x7fU)<=0x73U)
  printf("sense_key=0x%02x asc=0x%02x ascq=0x%02x format=descriptor\n",(unsigned)(sense[1]&0x0fU),(unsigned)sense[2],(unsigned)sense[3]);
 else if(length) puts("sense_decoded=unknown");
}

static int mode_sense10(int fd)
{
 unsigned char data[64]={0},sense[64]={0};
 /* UFS requires MODE SENSE(10); WP is byte 3 of its eight-byte header. */
 unsigned char cdb[10]={0x5a,0,0x3f,0,0,0,0,0,64,0};
 sg_io_hdr_t h={.interface_id='S',.dxfer_direction=SG_DXFER_FROM_DEV,.cmd_len=10,
  .mx_sb_len=64,.dxfer_len=64,.dxferp=data,.cmdp=cdb,.sbp=sense,.timeout=3000};
 errno=0;
 int result=ioctl(fd,SG_IO,&h),saved_errno=result?errno:0;
 printf("mode_sense10_rc=%d errno=%d scsi_status=%u masked_status=%u host=%u driver=%u info=%u resid=%d sense_len=%u\n",
  result,saved_errno,(unsigned)h.status,(unsigned)h.masked_status,(unsigned)h.host_status,
  (unsigned)h.driver_status,h.info,h.resid,(unsigned)h.sb_len_wr);
 report_sense(sense,(unsigned)h.sb_len_wr);
 if(result || h.status || h.masked_status || h.host_status || h.driver_status ||
    (h.info&SG_INFO_OK_MASK)!=SG_INFO_OK || h.sb_len_wr) {
  puts("lun_mode_write_protect=unknown reason=query_failed");return 1;
 }
 if(h.dxfer_len>sizeof(data) || h.resid<0 || (unsigned)h.resid>h.dxfer_len ||
    h.dxfer_len-(unsigned)h.resid<8U) {
  puts("lun_mode_write_protect=unknown reason=short_or_invalid_transfer");return 1;
 }
 unsigned mode_length=((unsigned)data[0]<<8)|(unsigned)data[1];
 if(mode_length<6U) {
  puts("lun_mode_write_protect=unknown reason=invalid_mode10_header");return 1;
 }
 /* An allocation-limited page body is allowed when the whole header arrived. */
 printf("lun_mode_write_protect=%u mode_header=10 received=%u declared_total=%u\n",
  (unsigned)((data[3]&0x80U)!=0U),h.dxfer_len-(unsigned)h.resid,mode_length+2U);
 return 0;
}

int main(int argc,char **argv)
{
 if(argc!=2 || strcmp(argv[1],"/dev/block/sdc")) {
  fputs("Expected audited chopin UFS LUN /dev/block/sdc\n",stderr);return 64;
 }
 int fd=open(argv[1],O_RDONLY|O_CLOEXEC|O_NONBLOCK);
 if(fd<0){perror("open UFS read-only");return 1;}
 struct stat st;
 if(fstat(fd,&st)||!S_ISBLK(st.st_mode)){close(fd);return 65;}
 int incomplete=0;
 unsigned boot=0;struct query q={.opcode=3,.idn=0,.size=4,.ptr=&boot};
 errno=0;int result=ioctl(fd,0x5388,&q);
 printf("boot_lun_query_rc=%d errno=%d\n",result,result?errno:0);
 if(!result) printf("boot_lun=%u\n",boot);
 else {puts("boot_lun=unknown");incomplete=1;}
 struct feature f={.opcode=0x55000001,.idn=2,.size=64};
 errno=0;result=ioctl(fd,0x5388,&f);
 printf("unit_descriptor_rc=%d errno=%d\n",result,result?errno:0);
 if(!result && f.data[0]>=6U && f.data[1]==2U)
  printf("unit_write_protect=%u boot_lun_id=%u unit_index=%u\n",(unsigned)f.data[5],(unsigned)f.data[4],(unsigned)f.data[2]);
 else {puts("unit_write_protect=unknown");incomplete=1;}
 if(mode_sense10(fd)) incomplete=1;
 puts("scope=read_queries_only; per-LU flags and mode WP do not prove individual ranges writable");
 printf("query_summary=%s\n",incomplete?"incomplete":"completed_writability_not_proven");
 close(fd);
 return incomplete?2:0;
}

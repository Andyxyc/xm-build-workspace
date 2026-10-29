/* Execute the real probe main with a memory-only ioctl transport. */
#define open fixture_open
#define fstat fixture_fstat
#define ioctl fixture_ioctl
#define close fixture_close
#define main actual_probe_main
#include "ufs_readonly.c"
#undef main
#undef open
#undef fstat
#undef ioctl
#undef close
#include <assert.h>
#include <stdarg.h>

static const char *fixture_case;
static unsigned fixture_calls;

int fixture_open(const char *path,int flags,...)
{
 assert(!strcmp(path,"/dev/block/sdc"));
 assert((flags&O_ACCMODE)==O_RDONLY && (flags&(O_TRUNC|O_CREAT|O_APPEND))==0);
 if(!strcmp(fixture_case,"open-error")){errno=EACCES;return -1;}
 return 42;
}
int fixture_fstat(int fd,struct stat *st)
{
 assert(fd==42);memset(st,0,sizeof(*st));
 st->st_mode=!strcmp(fixture_case,"not-a-block-device")?S_IFREG:S_IFBLK;
 return 0;
}
int fixture_close(int fd){assert(fd==42);return 0;}

int fixture_ioctl(int fd,unsigned long request,...)
{
 assert(fd==42);fixture_calls++;
 va_list args;va_start(args,request);void *argument=va_arg(args,void *);va_end(args);
 if(request==0x5388UL) {
  struct query *q=argument;
  if(q->opcode==3U) {
   assert(q->idn==0U && q->idx==0U && q->size==4U);
   if(!strcmp(fixture_case,"boot-query-error")){errno=EIO;return -1;}
   *(unsigned *)q->ptr=1U;return 0;
  }
  struct feature *f=argument;
  assert(f->opcode==0x55000001U && f->idn==2U && f->size==64U);
  if(!strcmp(fixture_case,"unit-query-error")){errno=EIO;return -1;}
  f->data[0]=64U;f->data[1]=2U;f->data[2]=2U;f->data[5]=0U;
  if(!strcmp(fixture_case,"unit-malformed")) f->data[0]=5U;
  return 0;
 }
 assert(request==SG_IO);
 sg_io_hdr_t *h=argument;
 const unsigned char expected[10]={0x5a,0,0x3f,0,0,0,0,0,64,0};
 assert(h->interface_id=='S' && h->dxfer_direction==SG_DXFER_FROM_DEV);
 assert(h->cmd_len==10U && !memcmp(h->cmdp,expected,sizeof(expected)));
 assert(h->mx_sb_len==64U && h->dxfer_len==64U && h->timeout==3000U);
 unsigned char *data=h->dxferp;
 data[1]=6U;h->resid=56;
 if(!strcmp(fixture_case,"wp-set")) data[3]=0x80U;
 if(!strcmp(fixture_case,"mode6-offset-decoy")) data[2]=0x80U;
 if(!strcmp(fixture_case,"allocation-limited-pages")){data[1]=254U;h->resid=0;}
 if(!strcmp(fixture_case,"short-transfer")) h->resid=57;
 if(!strcmp(fixture_case,"negative-residual")) h->resid=-1;
 if(!strcmp(fixture_case,"oversized-residual")) h->resid=65;
 if(!strcmp(fixture_case,"oversized-dxfer")) h->dxfer_len=65U;
 if(!strcmp(fixture_case,"short-declared-header")) data[1]=5U;
 if(!strcmp(fixture_case,"mode-ioctl-error")){errno=EIO;return -1;}
 if(!strcmp(fixture_case,"host-error")) h->host_status=1U;
 if(!strcmp(fixture_case,"driver-error")) h->driver_status=8U;
 if(!strcmp(fixture_case,"masked-status-error")) h->masked_status=1U;
 if(!strcmp(fixture_case,"info-error")) h->info=SG_INFO_CHECK;
 if(!strcmp(fixture_case,"oversized-sense")) h->sb_len_wr=65U;
 if(!strcmp(fixture_case,"sense-with-good-status")) {
  h->sb_len_wr=18U;h->sbp[0]=0x70U;h->sbp[2]=7U;h->sbp[7]=10U;h->sbp[12]=0x27U;h->sbp[13]=1U;
 }
 if(!strcmp(fixture_case,"fixed-sense") || !strcmp(fixture_case,"descriptor-sense")) {
  h->status=2U;h->driver_status=8U;h->info=SG_INFO_CHECK;
  if(!strcmp(fixture_case,"fixed-sense")) {
   h->sb_len_wr=18U;h->sbp[0]=0x70U;h->sbp[2]=7U;h->sbp[7]=10U;h->sbp[12]=0x27U;h->sbp[13]=1U;
  } else {h->sb_len_wr=8U;h->sbp[0]=0x72U;h->sbp[1]=7U;h->sbp[2]=0x27U;h->sbp[3]=1U;}
 }
 return 0;
}

int main(int argc,char **argv)
{
 assert(argc==2);fixture_case=argv[1];
 char *input[]={"ufs-readonly","/dev/block/sdc",NULL};
 if(!strcmp(fixture_case,"wrong-path")) input[1]="/dev/block/sda";
 int result=actual_probe_main(2,input);
 if(!strcmp(fixture_case,"wrong-path") || !strcmp(fixture_case,"open-error") || !strcmp(fixture_case,"not-a-block-device")) assert(fixture_calls==0U);
 else assert(fixture_calls==3U);
 return result;
}

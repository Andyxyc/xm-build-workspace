package cn.chopin.acceptanceprobe;
import android.os.Process;
import android.os.SystemClock;
import org.json.*;
import java.io.*;
import java.nio.*;
import java.nio.channels.FileChannel;
public final class Observation {
 public static String read(String path,int cap)throws Exception {
  try(InputStream in=new FileInputStream(path);ByteArrayOutputStream out=new ByteArrayOutputStream()){
   byte[] b=new byte[1024];int n;while(out.size()<cap&&(n=in.read(b,0,Math.min(b.length,cap-out.size())))>0)out.write(b,0,n);
   return out.toString("UTF-8");
  }
 }
 private static JSONObject access(String source,String target,int cls){
  JSONObject r=new JSONObject();try{
   try(RandomAccessFile f=new RandomAccessFile("/sys/fs/selinux/access","rw")){
    r.put("opened",true);f.write((source+" "+target+" "+cls).getBytes("US-ASCII"));f.seek(0);
    byte[] b=new byte[512];int n=f.read(b);r.put("response",n<0?"":new String(b,0,n,"US-ASCII").trim());
   }
  }catch(Exception e){try{r.put("error",e.toString());}catch(Exception ignored){}}
  return r;
 }
 public static JSONObject selinux()throws Exception{
  JSONObject r=new JSONObject();r.put("uid",Process.myUid());r.put("pid",Process.myPid());r.put("elapsed_ms",SystemClock.elapsedRealtime());r.put("root_requested",false);
  try{r.put("context",read("/proc/self/attr/current",512));}catch(Exception e){r.put("context_error",e.toString());}
  try{r.put("status",new JSONObject(NativeProbe.status()));}
  catch(Throwable e){r.put("status_error",e.toString());}
  try{
   int cls=Integer.parseInt(read("/sys/fs/selinux/class/process/index",64).trim());r.put("process_class",cls);
   r.put("positive",access("u:r:app_zygote:s0","u:r:app_zygote:s0",cls));
   r.put("negative",access("u:r:app_zygote:s0","u:r:chopin_invalid_probe:s0",cls));
   r.put("ksu",access("u:r:app_zygote:s0","u:r:ksu:s0",cls));
  }catch(Exception e){r.put("query_setup_error",e.toString());}
  return r;
 }
}

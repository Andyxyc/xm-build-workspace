package cn.chopin.acceptanceprobe;
import android.app.Activity;
import android.content.*;
import android.os.*;
import android.system.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.*;
import java.nio.channels.FileChannel;
public final class ProbeActivity extends Activity {
 private JSONObject report;private TextView view;private MappedByteBuffer mapped;private boolean bound;
 private final ServiceConnection conn=new ServiceConnection(){
  public void onServiceConnected(ComponentName n,IBinder b){try{report.put("isolated_service_connected",true);save();}catch(Exception ignored){}}
  public void onServiceDisconnected(ComponentName n){}
 };
 private void save()throws Exception{
  String text=report.toString(2);File temp=new File(getFilesDir(),"latest.tmp"),target=new File(getFilesDir(),"latest.json");
  try(FileOutputStream out=new FileOutputStream(temp)){out.write(text.getBytes("UTF-8"));out.getFD().sync();}
  if(!temp.renameTo(target))throw new IOException("Report rename failed");view.setText(text);
 }
 private JSONObject file(String name)throws Exception{
  File f=new File(getFilesDir(),name);JSONObject r=new JSONObject();r.put("exists",f.exists());
  try{StructStat s=Os.stat(f.getAbsolutePath());r.put("ino",s.st_ino);r.put("size",s.st_size);r.put("uid",s.st_uid);r.put("gid",s.st_gid);r.put("atime",s.st_atime);r.put("mtime",s.st_mtime);r.put("ctime",s.st_ctime);}
  catch(Exception e){r.put("stat_error",e.toString());}
  try{r.put("content",Observation.read(f.getAbsolutePath(),1024));}catch(Exception e){r.put("open_error",e.toString());}
  return r;
 }
 @Override public void onCreate(Bundle state){
  super.onCreate(state);view=new TextView(this);view.setPadding(24,32,24,24);ScrollView scroll=new ScrollView(this);scroll.addView(view);setContentView(scroll);
  try{
   String mode=getIntent().getStringExtra("mode");if(mode==null)mode="check";
   report=new JSONObject();report.put("run_id",getIntent().getStringExtra("run_id"));report.put("mode",mode);report.put("elapsed_ms",SystemClock.elapsedRealtime());report.put("uid",android.os.Process.myUid());report.put("root_requested",false);
   if(mode.equals("prepare"))for(String n:new String[]{"path-probe.txt","stat-probe.txt","map-probe.txt"}){
    File f=new File(getFilesDir(),n);if(!f.exists())try(FileOutputStream out=new FileOutputStream(f)){out.write(("Chopin "+n+"\n").getBytes("UTF-8"));out.getFD().sync();}
   }
   for(String n:new String[]{"path-probe.txt","stat-probe.txt","map-probe.txt"})report.put(n,file(n));
   StructUtsname u=Os.uname();report.put("uname_release",u.release);report.put("uname_version",u.version);
   report.put("cpuinfo",Observation.read("/proc/cpuinfo",16384));report.put("selinux",Observation.selinux());
   if(mode.equals("map")){
    File f=new File(getFilesDir(),"map-probe.txt");try(FileInputStream in=new FileInputStream(f)){mapped=in.getChannel().map(FileChannel.MapMode.READ_ONLY,0,f.length());report.put("mapped_first_byte",mapped.get(0)&255);}
    String maps=Observation.read("/proc/self/maps",2097152);
    if(maps.length()>=2097152)throw new IOException("Maps observation truncated");
    long inode=Os.stat(f.getAbsolutePath()).st_ino;boolean found=false;
    for(String line:maps.split("\n")){
     String[] columns=line.trim().split("\\s+",6);
     if(columns.length==6 && columns[4].equals(Long.toString(inode)) && columns[5].endsWith("/"+getPackageName()+"/files/map-probe.txt"))found=true;
    }
    report.put("maps_bytes",maps.length());report.put("map_path_visible",found);
   }
   report.put("self_priority",new JSONObject(NativeProbe.priority(android.os.Process.myUid())));
   int targetPid=getIntent().getIntExtra("scheduler_pid",-1);
   if(targetPid>1)report.put("scheduler_query",new JSONObject(NativeProbe.scheduler(targetPid)));
   String socket=getIntent().getStringExtra("socket_path");
   if(socket!=null && socket.startsWith(getFilesDir().getAbsolutePath()+"/chopin-avc-"))report.put("local_socket",new JSONObject(NativeProbe.connect(socket)));
   if(mode.equals("zygote")){bound=bindService(new Intent(this,IsolatedProbe.class),conn,BIND_AUTO_CREATE);report.put("isolated_service_bind",bound);}
   save();
  }catch(Exception e){try{if(report==null)report=new JSONObject();report.put("error",e.toString());save();}catch(Exception ignored){view.setText(e.toString());}}
 }
 @Override public void onDestroy(){if(bound)unbindService(conn);super.onDestroy();}
}

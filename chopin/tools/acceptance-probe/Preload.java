package cn.chopin.acceptanceprobe;
import android.app.ZygotePreload;
import android.content.pm.ApplicationInfo;
import android.util.Log;
public final class Preload implements ZygotePreload {
 public Preload(){}
 @Override public void doPreload(ApplicationInfo info){
  try{Log.i("ChopinZygoteProbe",Observation.selinux().put("scope","APP_ZYGOTE_RAW_QUERY_ONLY").toString());}
  catch(Exception e){Log.e("ChopinZygoteProbe","probe_error:"+e);}
 }
}

package cn.chopin.acceptanceprobe;
import android.app.Service;
import android.content.Intent;
import android.os.Binder;
import android.os.IBinder;
public final class IsolatedProbe extends Service {
 @Override public IBinder onBind(Intent intent){return new Binder();}
}

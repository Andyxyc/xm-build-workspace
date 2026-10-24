package cn.chopin.kernelprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Process;
import android.widget.TextView;
import android.system.Os;
import android.system.StructStat;
import android.hardware.camera2.*;
import android.media.Image;
import android.media.ImageReader;
import android.graphics.ImageFormat;
import android.graphics.BitmapFactory;
import android.util.Size;
import org.json.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Visible, unprivileged probe. No network permission, root request or daemon. */
public final class ProbeActivity extends Activity {
    private TextView view;
    private HandlerThread thread;
    private CameraDevice camera;
    private ImageReader reader;
    private final AtomicBoolean done = new AtomicBoolean(false);
    private JSONObject report;
    private String mode;
    private static String read(File f, int limit) throws IOException {
        try (InputStream in = new FileInputStream(f); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] b = new byte[2048]; int n;
            while (out.size() < limit && (n = in.read(b, 0, Math.min(b.length, limit-out.size()))) > 0) out.write(b,0,n);
            return out.toString("UTF-8");
        }
    }
    private static void write(File f, byte[] b) throws IOException {
        try (FileOutputStream out = new FileOutputStream(f)) { out.write(b); out.getFD().sync(); }
    }
    private JSONObject fileInfo(String name) throws JSONException {
        File f = new File(getFilesDir(),name); JSONObject r = new JSONObject();
        r.put("path",f.getAbsolutePath());r.put("exists",f.exists());
        try { StructStat s=Os.stat(f.getAbsolutePath());r.put("stat_size",s.st_size);r.put("stat_ino",s.st_ino);r.put("stat_uid",s.st_uid);r.put("stat_gid",s.st_gid);r.put("stat_mtime",s.st_mtime); }
        catch (Exception e) { r.put("stat_error",e.toString()); }
        try { r.put("content",read(f,1024)); } catch(Exception e) { r.put("open_error",e.toString()); }
        return r;
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);view=new TextView(this);view.setPadding(24,32,24,24);setContentView(view);
        mode=getIntent().getStringExtra("mode");if(mode==null)mode="check";
        if(!Arrays.asList("prepare","check","cameras","capture").contains(mode)){view.setText("未知测试模式");return;}
        try {
            report=new JSONObject();report.put("mode",mode);report.put("uid",Process.myUid());report.put("timestamp_ms",System.currentTimeMillis());
            try {report.put("selinux_context",read(new File("/proc/self/attr/current"),1024));}catch(Exception e){report.put("context_error",e.toString());}
            if(mode.equals("prepare")) {
                for(String n:Arrays.asList("path-probe.txt","stat-probe.txt")) {
                    File f=new File(getFilesDir(),n);if(!f.exists())write(f,"Chopin kernel probe\n".getBytes("UTF-8"));
                }
                new File(getFilesDir(),"mount-probe").mkdir();
            }
            report.put("path_probe",fileInfo("path-probe.txt"));report.put("stat_probe",fileInfo("stat-probe.txt"));
            report.put("directory_listing",new JSONArray(Arrays.asList(getFilesDir().list())));
            try {report.put("mountinfo",read(new File("/proc/self/mountinfo"),65536));}catch(Exception e){report.put("mountinfo_error",e.toString());}
            if(!mode.equals("cameras")&&!mode.equals("capture")){finishReport(null);return;}
            CameraManager manager=(CameraManager)getSystemService(CAMERA_SERVICE);
            JSONArray cams=new JSONArray();
            for(String id:manager.getCameraIdList()) {
                CameraCharacteristics c=manager.getCameraCharacteristics(id);JSONObject o=new JSONObject();o.put("id",id);o.put("lens_facing",c.get(CameraCharacteristics.LENS_FACING));o.put("sensor_orientation",c.get(CameraCharacteristics.SENSOR_ORIENTATION));
                if(android.os.Build.VERSION.SDK_INT>=28)o.put("physical_ids",new JSONArray(c.getPhysicalCameraIds()));
                cams.put(o);
            }
            report.put("cameras_exposed_to_this_app",cams);
            if(mode.equals("capture")){capture(manager);return;}
            finishReport(null);
        }catch(Exception e){finishReport(e);}
    }
    private void capture(CameraManager manager) throws Exception {
        String id=getIntent().getStringExtra("camera_id");if(id==null)id="0";
        if(!id.matches("[A-Za-z0-9_.-]{1,32}"))throw new IllegalArgumentException("Invalid camera id");
        final String selected=id;report.put("selected_camera",id);view.setText("正在拍摄摄像头测试照片，完成后保存在本应用私有目录。");
        Size[] sizes=manager.getCameraCharacteristics(id).get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP).getOutputSizes(ImageFormat.JPEG);
        if(sizes==null||sizes.length==0)throw new IllegalStateException("No JPEG sizes");
        Size size=sizes[0];for(Size s:sizes)if((long)s.getWidth()*s.getHeight()<(long)size.getWidth()*size.getHeight())size=s;
        for(Size s:sizes)if(s.getWidth()<=1920&&s.getHeight()<=1920&&(long)s.getWidth()*s.getHeight()>(long)size.getWidth()*size.getHeight())size=s;
        thread=new HandlerThread("ChopinProbe");thread.start();Handler handler=new Handler(thread.getLooper());
        reader=ImageReader.newInstance(size.getWidth(),size.getHeight(),ImageFormat.JPEG,2);
        reader.setOnImageAvailableListener(r->{
            try(Image image=r.acquireLatestImage()) {
                if(image==null||done.get())return;
                ByteBuffer buf=image.getPlanes()[0].getBuffer();byte[] bytes=new byte[buf.remaining()];buf.get(bytes);
                File out=new File(getFilesDir(),"camera-"+selected+"-"+System.currentTimeMillis()+".jpg");write(out,bytes);
                BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeFile(out.getAbsolutePath(),options);
                report.put("jpeg_path",out.getAbsolutePath());report.put("jpeg_bytes",bytes.length);report.put("jpeg_width",options.outWidth);report.put("jpeg_height",options.outHeight);
                if(options.outWidth<=0||options.outHeight<=0)throw new IOException("JPEG decode failed");
                finishReport(null);
            }catch(Exception e){finishReport(e);}
        },handler);
        handler.postDelayed(()->finishReport(new IOException("Camera capture timeout")),30000);
        manager.openCamera(id,new CameraDevice.StateCallback(){
            @Override public void onOpened(CameraDevice d){
                if(done.get()){d.close();return;}camera=d;
                try {d.createCaptureSession(Collections.singletonList(reader.getSurface()),new CameraCaptureSession.StateCallback(){
                    @Override public void onConfigured(CameraCaptureSession session){
                        try {CaptureRequest.Builder req=d.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE);req.addTarget(reader.getSurface());req.set(CaptureRequest.CONTROL_MODE,CaptureRequest.CONTROL_MODE_AUTO);session.capture(req.build(),null,handler);}
                        catch(Exception e){finishReport(e);}
                    }
                    @Override public void onConfigureFailed(CameraCaptureSession session){finishReport(new IOException("Capture session configuration failed"));}
                },handler);}catch(Exception e){finishReport(e);}
            }
            @Override public void onDisconnected(CameraDevice d){d.close();finishReport(new IOException("Camera disconnected"));}
            @Override public void onError(CameraDevice d,int error){d.close();finishReport(new IOException("Camera error "+error));}
        },handler);
    }
    @Override public void onDestroy() {
        if(!done.get())finishReport(new IOException("Activity destroyed before completion"));
        super.onDestroy();
    }
    private void finishReport(Exception error) {
        if(!done.compareAndSet(false,true))return;
        try {
            if(report==null)report=new JSONObject();report.put("probe_status",error==null?"OBSERVATION_RECORDED":"ERROR");
            report.put("limitation","An observation only; no automatic claim of full camera, SUSFS or power acceptance");
            if(error!=null)report.put("error",error.toString());
            String text=report.toString(2);write(new File(getFilesDir(),"report-"+mode+"-"+System.currentTimeMillis()+".json"),text.getBytes("UTF-8"));
            runOnUiThread(()->view.setText(text));
        }catch(Exception e){runOnUiThread(()->view.setText("无法保存测试记录："+e));}
        finally {if(camera!=null)camera.close();if(reader!=null)reader.close();if(thread!=null)thread.quitSafely();}
    }
}

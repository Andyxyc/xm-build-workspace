package cn.chopin.queryprobe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Process;
import android.system.Os;
import android.system.OsConstants;
import android.system.StructStat;
import android.system.StructUtsname;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONObject;
import org.json.JSONArray;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;

/** An ordinary app observer: no su command, network, policy write or service. */
public final class QueryActivity extends Activity {
    private static String read(String path, int cap) throws IOException {
        try (InputStream in = new FileInputStream(path);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] b = new byte[1024]; int n;
            while (out.size() < cap && (n = in.read(b, 0, Math.min(b.length, cap-out.size()))) > 0)
                out.write(b, 0, n);
            return out.toString("UTF-8");
        }
    }
    private static JSONObject path(String name) throws Exception {
        JSONObject r = new JSONObject(); r.put("path", name);
        r.put("java_exists", new File(name).exists());
        try {
            StructStat s = Os.stat(name);
            r.put("stat_ok", true); r.put("size", s.st_size); r.put("mode", s.st_mode);
            r.put("uid", s.st_uid); r.put("gid", s.st_gid);
        } catch (Exception e) { r.put("stat_error", e.toString()); }
        try { r.put("access_F_OK", Os.access(name, OsConstants.F_OK)); }
        catch (Exception e) { r.put("access_F_OK_error", e.toString()); }
        try { r.put("access_X_OK", Os.access(name, OsConstants.X_OK)); }
        catch (Exception e) { r.put("access_X_OK_error", e.toString()); }
        return r;
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView v = new TextView(this); v.setPadding(24, 24, 24, 24);
        v.setTextIsSelectable(true); ScrollView s = new ScrollView(this); s.addView(v); setContentView(s);
        JSONObject report = new JSONObject();
        try {
            report.put("scope", "ORDINARY_APP_READ_ONLY_OBSERVATIONS_NOT_CHUNQIU_PASS");
            report.put("uid", Process.myUid()); report.put("pid", Process.myPid());
            report.put("timestamp_ms", System.currentTimeMillis());
            report.put("root_requested", false);
            StructUtsname u = Os.uname(); JSONObject uname = new JSONObject();
            uname.put("release",u.release); uname.put("version",u.version); uname.put("machine",u.machine);
            report.put("uname",uname);
            for (String name : new String[]{"/proc/self/attr/current", "/proc/version",
                    "/proc/sys/kernel/osrelease", "/proc/sys/kernel/version", "/proc/cpuinfo",
                    "/sys/fs/selinux/enforce", "/sys/fs/selinux/deny_unknown"}) {
                try { report.put(name,read(name,16384)); }
                catch(Exception e) { report.put(name+"_error", e.toString()); }
            }
            JSONArray paths = new JSONArray();
            for (String name : new String[]{"/system/bin/su", "/system/xbin/su", "/sbin/su",
                    "/apex/com.android.virt/bin/su", "/system/bin/sh"}) paths.put(path(name));
            report.put("path_views",paths);
            // This directly exercises the status mmap page selected at open.
            JSONObject status = new JSONObject();
            try (FileInputStream in = new FileInputStream("/sys/fs/selinux/status")) {
                ByteBuffer page = in.getChannel().map(FileChannel.MapMode.READ_ONLY,0,20);
                page.order(ByteOrder.LITTLE_ENDIAN);
                String[] names = {"version","sequence","enforcing","policyload","deny_unknown"};
                for (String name:names) status.put(name, ((long)page.getInt()) & 0xffffffffL);
            } catch (Exception e) { status.put("error", e.toString()); }
            report.put("selinux_status_mmap",status);
            // Opening this transaction node does not submit a query or change policy.
            try (RandomAccessFile access = new RandomAccessFile("/sys/fs/selinux/access", "rw")) {
                report.put("selinux_access_open_rw", true);
            } catch (Exception e) { report.put("selinux_access_open_rw_error", e.toString()); }
        } catch (Exception e) {
            try {report.put("incomplete_error",e.toString());} catch(Exception ignored) {}
        }
        try {
            String text=report.toString(2);
            try (FileOutputStream out = openFileOutput("latest-query.json", MODE_PRIVATE)) {
                out.write(text.getBytes("UTF-8")); out.getFD().sync();
            }
            v.setText(text);
        } catch(Exception e) { v.setText("Report write error: "+e); }
    }
}

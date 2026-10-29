package cn.chopin.priorityprobe;

import android.app.Activity;
import android.content.pm.ApplicationInfo;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.json.JSONObject;

public final class PriorityActivity extends Activity {
    private void save(JSONObject report, String runId, TextView view) throws Exception {
        byte[] data = (report.toString(2) + "\n").getBytes(StandardCharsets.UTF_8);
        File history = new File(getFilesDir(), "priority-" + runId + ".json");
        if (!history.createNewFile()) throw new IllegalStateException("Run report already exists");
        try (FileOutputStream stream = new FileOutputStream(history)) {
            stream.write(data);
            stream.getFD().sync();
        }
        File temporary = File.createTempFile("priority-latest-", ".tmp", getFilesDir());
        try (FileOutputStream stream = new FileOutputStream(temporary)) {
            stream.write(data);
            stream.getFD().sync();
        }
        if (!temporary.renameTo(new File(getFilesDir(), "latest.json")))
            throw new IllegalStateException("Latest report rename failed");
        view.setText(new String(data, StandardCharsets.UTF_8));
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView view = new TextView(this);
        view.setPadding(24, 32, 24, 24);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(view);
        setContentView(scroll);
        String runId = UUID.randomUUID().toString();
        JSONObject report = new JSONObject();
        try {
            report.put("schema", 1);
            report.put("run_id", runId);
            report.put("observer_package", getPackageName());
            report.put("source_commit", BuildInfo.SOURCE_COMMIT);
            report.put("native_sha256", BuildInfo.NATIVE_SHA256);
            report.put("caller_uid_java", Process.myUid());
            report.put("caller_pid_java", Process.myPid());
            report.put("elapsed_start_ms", SystemClock.elapsedRealtime());
            report.put("root_requested", false);
            report.put("scheduling_writes", false);
            report.put("network_used", false);
            report.put("package_manager_verified", false);
            String requested = getIntent().getStringExtra("controller_run_id");
            if (requested == null || !UUID.fromString(requested).toString().equals(requested))
                throw new IllegalArgumentException("A canonical controller_run_id UUID is required");
            report.put("controller_run_id", requested);
            if (!getIntent().hasExtra("probe2_uid") || !getIntent().hasExtra("probe3_uid"))
                throw new IllegalArgumentException("Both controller UIDs are required");
            int extra2 = getIntent().getIntExtra("probe2_uid", -1);
            int extra3 = getIntent().getIntExtra("probe3_uid", -1);
            ApplicationInfo info2 = getPackageManager().getApplicationInfo(TargetUids.PROBE2, 0);
            ApplicationInfo info3 = getPackageManager().getApplicationInfo(TargetUids.PROBE3, 0);
            int[] targets = TargetUids.validate(Process.myUid(), extra2, info2.uid, extra3, info3.uid);
            JSONObject packages = new JSONObject();
            packages.put(TargetUids.PROBE2, targets[0]);
            packages.put(TargetUids.PROBE3, targets[1]);
            report.put("target_package_uids", packages);
            report.put("package_manager_verified", true);
            JSONObject observation = new JSONObject(NativePriority.observe(targets[0], targets[1]));
            report.put("native", observation);
            report.put("status", observation.optString("status").equals("observed") ? "observed" : "rejected_native_context");
        } catch (Exception | LinkageError failure) {
            try {
                report.put("status", "rejected");
                report.put("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
            } catch (Exception ignored) {}
        }
        try {
            report.put("elapsed_end_ms", SystemClock.elapsedRealtime());
            save(report, runId, view);
        } catch (Exception failure) {
            view.setText("Report save failed: " + failure.toString());
        }
    }
}

package cn.chopin.acceptanceprobe;
public final class NativeProbe {
 static { System.loadLibrary("chopin_probe"); }
 public static native String status();
 public static native String connect(String path);
 public static native String priority(int uid);
}

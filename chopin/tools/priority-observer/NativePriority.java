package cn.chopin.priorityprobe;

public final class NativePriority {
    static { System.loadLibrary("chopin_priority"); }
    private NativePriority() {}
    public static native String observe(int packageManagerUid2, int packageManagerUid3);
}

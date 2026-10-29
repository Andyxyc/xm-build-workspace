package cn.chopin.priorityprobe;

public final class TargetUids {
    public static final String PROBE2 = "cn.chopin.acceptanceprobe2";
    public static final String PROBE3 = "cn.chopin.acceptanceprobe3";

    private TargetUids() {}

    public static int[] validate(int caller, int extra2, int actual2, int extra3, int actual3) {
        if (caller < 10000 || actual2 < 10000 || actual3 < 10000)
            throw new IllegalArgumentException("An ordinary app UID is required");
        if (extra2 != actual2 || extra3 != actual3)
            throw new IllegalArgumentException("Controller UID differs from PackageManager");
        if (actual2 == actual3 || actual2 == caller || actual3 == caller)
            throw new IllegalArgumentException("The three apps must have distinct UIDs");
        if (caller / 100000 != actual2 / 100000 || caller / 100000 != actual3 / 100000)
            throw new IllegalArgumentException("The apps must belong to the same Android user");
        return new int[] {actual2, actual3};
    }
}

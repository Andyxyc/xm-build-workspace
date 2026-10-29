package cn.chopin.priorityprobe;

public final class TargetUidsFixture {
    public static void main(String[] args) {
        int[][] valid = {{10004,10002,10002,10003,10003}, {110004,110002,110002,110003,110003}};
        int[][] invalid = {
            {0,10002,10002,10003,10003}, {9999,10002,10002,10003,10003},
            {10004,-1,10002,10003,10003}, {10004,10002,10002,-1,10003},
            {10004,10009,10002,10003,10003}, {10004,10002,10002,10009,10003},
            {10004,10004,10004,10003,10003}, {10004,10002,10002,10004,10004},
            {10004,10002,10002,10002,10002}, {10004,1000,1000,10003,10003},
            {10004,110002,110002,10003,10003}, {110004,10002,10002,110003,110003},
        };
        for (int[] input : valid) {
            int[] actual = TargetUids.validate(input[0], input[1], input[2], input[3], input[4]);
            if (actual[0] != input[2] || actual[1] != input[4]) throw new AssertionError("Wrong UID pair");
        }
        for (int[] input : invalid) {
            boolean rejected = false;
            try { TargetUids.validate(input[0], input[1], input[2], input[3], input[4]); }
            catch (IllegalArgumentException expected) { rejected = true; }
            if (!rejected) throw new AssertionError("Invalid UID pair was accepted");
        }
        System.out.println("{\"status\":\"PASS_UID_GATE_INTEGER_FIXTURES_ONLY\",\"cases\":" +
                (valid.length + invalid.length) + ",\"android_package_manager_tested\":false}");
    }
}

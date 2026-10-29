#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include "priority_semantics.h"

int main(void) {
    unsigned int cases = 0;
    for (long raw = 1; raw <= 40; ++raw) {
        struct priority_result value = priority_decode(raw);
        assert(value.raw == raw && value.error == 0 && value.valid_success);
        assert(value.nice >= -20 && value.nice <= 19 && value.nice + raw == 20);
        ++cases;
    }
    assert(priority_decode(1).nice == 19);
    assert(priority_decode(20).nice == 0);
    assert(priority_decode(21).nice == -1);
    assert(priority_decode(40).nice == -20);
    for (long error = 1; error <= 4095; ++error) {
        struct priority_result value = priority_decode(-error);
        assert(value.error == error && !value.valid_success);
        ++cases;
    }
    const long invalid[] = {0, 41, -4096, LONG_MIN, LONG_MAX};
    for (unsigned int i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        struct priority_result value = priority_decode(invalid[i]);
        assert(!value.valid_success && !value.error);
        ++cases;
    }
    printf("{\"status\":\"PASS_RAW_PRIORITY_DECODER_HOST_FIXTURES_ONLY\",\"cases\":%u,"
           "\"actual_svc_executed\":false,\"android_runtime_tested\":false}\n", cases);
    return 0;
}

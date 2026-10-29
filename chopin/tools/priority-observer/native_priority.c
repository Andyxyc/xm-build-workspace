/* Only priority reads for this app and the two PackageManager-checked probes. */
#include <asm/unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <jni.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include "priority_semantics.h"

#if !defined(__aarch64__)
#error This observer must use the real ARM64 syscall ABI.
#endif
_Static_assert(__NR_getpriority == 141, "Unexpected ARM64 getpriority number");
_Static_assert(PRIO_PROCESS == 0 && PRIO_USER == 2, "Unexpected priority API constants");

static long direct_call(long number, long argument0, long argument1) {
    register long x8 __asm__("x8") = number;
    register long x0 __asm__("x0") = argument0;
    register long x1 __asm__("x1") = argument1;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1) : "memory", "cc");
    return x0;
}

static int64_t monotonic_ns(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return -1;
    return (int64_t)value.tv_sec * 1000000000LL + value.tv_nsec;
}

static int ordinary_context(char *context, size_t capacity) {
    int fd = open("/proc/self/attr/current", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    ssize_t length = read(fd, context, capacity - 1);
    close(fd);
    if (length <= 0 || (size_t)length >= capacity - 1) { context[0] = 0; return 0; }
    context[length] = 0;
    context[strcspn(context, "\n")] = 0;
    for (const char *p = context; *p; ++p) {
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || strchr("_:,.-", *p))) { context[0] = 0; return 0; }
    }
    if (strncmp(context, "u:r:untrusted_app", 17)) return 0;
    const char *suffix = context + 17;
    if (*suffix == '_') {
        ++suffix;
        if (*suffix < '0' || *suffix > '9') return 0;
        while (*suffix >= '0' && *suffix <= '9') ++suffix;
    }
    return strncmp(suffix, ":s0", 3) == 0 && (suffix[3] == 0 || suffix[3] == ':');
}

static int append(char *out, size_t capacity, size_t *used, const char *format, ...) {
    if (*used >= capacity) return 0;
    va_list args;
    va_start(args, format);
    int count = vsnprintf(out + *used, capacity - *used, format, args);
    va_end(args);
    if (count < 0 || (size_t)count >= capacity - *used) return 0;
    *used += (size_t)count;
    return 1;
}

static int append_query(char *out, size_t capacity, size_t *used,
                        const char *name, int which, int who) {
    int64_t start = monotonic_ns();
    long raw = direct_call(__NR_getpriority, which, who);
    struct priority_result decoded = priority_decode(raw);
    errno = 0;
    long system_value = syscall(__NR_getpriority, which, who);
    int system_errno = errno;
    errno = 0;
    int nice = getpriority(which, (id_t)who);
    int nice_errno = errno;
    int64_t end = monotonic_ns();
    int agree = decoded.valid_success
        ? system_value == raw && system_errno == 0 && nice == decoded.nice && nice_errno == 0
        : decoded.error && system_value == -1 && system_errno == decoded.error &&
          nice == -1 && nice_errno == decoded.error;
    char mapped[32];
    if (decoded.valid_success) snprintf(mapped, sizeof(mapped), "%d", decoded.nice);
    else snprintf(mapped, sizeof(mapped), "null");
    return append(out, capacity, used,
        "{\"name\":\"%s\",\"which\":%d,\"who\":%d,\"direct_arm64_svc\":true,"
        "\"raw_return\":%ld,\"raw_errno\":%d,\"raw_success_1_to_40\":%s,"
        "\"raw_out_of_contract\":%s,\"interpreted_nice\":%s,"
        "\"libc_syscall_return\":%ld,\"libc_syscall_errno\":%d,"
        "\"libc_getpriority_nice\":%d,\"libc_getpriority_errno\":%d,"
        "\"sequential_semantics_agree\":%s,\"start_monotonic_ns\":%" PRId64 ","
        "\"end_monotonic_ns\":%" PRId64 ",\"timing_valid\":%s}",
        name, which, who, raw, decoded.error,
        decoded.valid_success ? "true" : "false",
        !decoded.valid_success && !decoded.error ? "true" : "false", mapped,
        system_value, system_errno, nice, nice_errno, agree ? "true" : "false",
        start, end, start >= 0 && end >= start ? "true" : "false");
}

JNIEXPORT jstring JNICALL Java_cn_chopin_priorityprobe_NativePriority_observe(
        JNIEnv *environment, jclass type, jint probe2, jint probe3) {
    (void)type;
    long raw_uid = direct_call(__NR_getuid, 0, 0);
    long raw_euid = direct_call(__NR_geteuid, 0, 0);
    uid_t uid = getuid(), euid = geteuid();
    char context[512] = {0};
    int context_ok = ordinary_context(context, sizeof(context));
    if (raw_uid < 10000 || raw_uid != raw_euid || raw_uid != (long)uid || uid != euid ||
        probe2 < 10000 || probe3 < 10000 || probe2 == probe3 ||
        (long)probe2 == raw_uid || (long)probe3 == raw_uid ||
        probe2 / 100000 != raw_uid / 100000 || probe3 / 100000 != raw_uid / 100000 || !context_ok) {
        char error[1024];
        snprintf(error, sizeof(error),
            "{\"status\":\"rejected_identity_or_context\",\"caller_uid_direct\":%ld,"
            "\"caller_euid_direct\":%ld,\"caller_uid_libc\":%lu,\"caller_pid\":%ld,"
            "\"caller_context\":\"%s\",\"ordinary_app_context\":%s,\"queries\":[]}",
            raw_uid, raw_euid, (unsigned long)uid, (long)getpid(), context, context_ok ? "true" : "false");
        return (*environment)->NewStringUTF(environment, error);
    }
    char out[8192];
    size_t used = 0;
    int ok = append(out, sizeof(out), &used,
        "{\"status\":\"observed\",\"caller_uid_direct\":%ld,\"caller_euid_direct\":%ld,"
        "\"caller_uid_libc\":%lu,\"caller_pid\":%ld,\"caller_context\":\"%s\","
        "\"ordinary_app_context\":true,\"syscall_number\":%d,\"queries_are_sequential\":true,\"queries\":[",
        raw_uid, raw_euid, (unsigned long)uid, (long)getpid(), context, __NR_getpriority);
    const char *names[] = {"self_uid", "self_user_zero", "self_process_zero", "probe2", "probe3"};
    int which[] = {PRIO_USER, PRIO_USER, PRIO_PROCESS, PRIO_USER, PRIO_USER};
    int who[] = {(int)uid, 0, 0, probe2, probe3};
    for (int index = 0; ok && index < 5; ++index) {
        if (index) ok = append(out, sizeof(out), &used, ",");
        if (ok) ok = append_query(out, sizeof(out), &used, names[index], which[index], who[index]);
    }
    if (ok) ok = append(out, sizeof(out), &used, "]}");
    return (*environment)->NewStringUTF(environment,
        ok ? out : "{\"status\":\"report_buffer_error\",\"queries\":[]}");
}

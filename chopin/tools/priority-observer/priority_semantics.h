#ifndef CHOPIN_PRIORITY_SEMANTICS_H
#define CHOPIN_PRIORITY_SEMANTICS_H

struct priority_result {
    long raw;
    int error;
    int valid_success;
    int nice;
};

static inline struct priority_result priority_decode(long raw) {
    struct priority_result result = {raw, 0, 0, 0};
    if (raw <= -1 && raw >= -4095) result.error = (int)-raw;
    else if (raw >= 1 && raw <= 40) {
        result.valid_success = 1;
        result.nice = 20 - (int)raw;
    }
    return result;
}

#endif

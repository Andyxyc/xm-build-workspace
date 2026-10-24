/* SPDX-License-Identifier: GPL-2.0 */
#ifndef CHOPIN_VENDOR_REFCNT_TRACE_H
#define CHOPIN_VENDOR_REFCNT_TRACE_H
/* Public data layout used directly by the stock MTK WLAN adaptor. */
struct refcnt_trace {
    int refcnt;
    unsigned int info;
    unsigned int entry_nr;
    unsigned long time;
    unsigned long entry[64];
};
extern unsigned int trace_idx;
extern struct refcnt_trace trace_array[40960];
#endif

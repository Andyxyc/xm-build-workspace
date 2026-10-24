/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Real storage used by the stock WLAN adaptor's inlined MTK dev_put/dev_hold
 * reference tracking. The stock module writes these records directly.
 *
 * Common MTK layout reference (GPL-2.0): realme-kernel-opensource/
 * realmeC3-narzo10A-narzo10-6i-kernel-source, e469e38485983832347674c504fdc372ea41d4bb,
 * include/linux/netdevice.h and net/core/dev.c.
 * Stock ELF relocations and instructions establish the chopin constants:
 * 64 stack entries, 536 bytes per record, 40960 records. Actual genksyms CRCs
 * must be checked after compilation; no symbol version is overridden here.
 * No additional recording hooks, timers, threads or per-event logging.
 */
#include <linux/export.h>
#include "chopin_vendor_refcnt_trace.h"

typedef char chopin_refcnt_record_must_be_536_bytes[
    sizeof(struct refcnt_trace) == 536 ? 1 : -1];

unsigned int trace_idx;
EXPORT_SYMBOL(trace_idx);

struct refcnt_trace trace_array[40960];
EXPORT_SYMBOL(trace_array);

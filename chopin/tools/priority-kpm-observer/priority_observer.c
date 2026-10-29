/* SPDX-License-Identifier: GPL-2.0-only */
#include <compiler.h>
#include <kpmodule.h>
#include <kallsyms.h>
#include "observer_core.h"

KPM_NAME(OBS_NAME);
KPM_VERSION("1.0");
KPM_LICENSE("GPL v2");
KPM_AUTHOR("Chopin diagnostics");
KPM_DESCRIPTION("Exact r18 legacy artifact: four NULL/scalar states only; no hooks or target writes");

struct resolved_symbols {
    unsigned long addresses[OBS_SYMBOL_COUNT];
    unsigned int counts[OBS_SYMBOL_COUNT];
};
static struct resolved_symbols resolved;
static int initialized;

/* Scan once at load. Count every full-name match, including local symbols. */
static int collect(void *opaque, const char *name, struct module *owner, unsigned long addr)
{
    struct resolved_symbols *r = opaque;
    unsigned int i;
    (void)owner;
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) {
        if (obs_equal(name, obs_symbols[i].name)) {
            if (r->counts[i] < 2U) ++r->counts[i];
            r->addresses[i] = addr;
        }
    }
    return 0;
}

static unsigned long resolve(void *opaque, unsigned int i)
{
    const struct resolved_symbols *r = opaque;
    return r->counts[i] == 1U ? r->addresses[i] : 0;
}

static unsigned char read_text(void *unused, unsigned long address)
{
    (void)unused;
    return *(const volatile unsigned char *)address;
}

static unsigned long read_slot(void *unused, unsigned long address, unsigned int width)
{
    (void)unused;
    /* GCC ARM64 acquire loads: LDAR/LDARB, with no dereference of loaded pointer. */
    if (width == 8) return __atomic_load_n((const unsigned long *)address, __ATOMIC_ACQUIRE);
    if (width == 4) return __atomic_load_n((const unsigned int *)address, __ATOMIC_ACQUIRE);
    return __atomic_load_n((const unsigned char *)address, __ATOMIC_ACQUIRE);
}

static const struct obs_io io = {&resolved, resolve, read_slot, read_text};

static long init(const char *args, const char *event, void *reserved)
{
    long result;
    unsigned int i;
    (void)event; (void)reserved;
    if (!obs_equal(args, OBS_INIT_ARGS) || !kallsyms_on_each_symbol || !kallsyms_lookup_name)
        return -OBS_EINVAL;
    initialized = 0;
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) {
        resolved.addresses[i] = 0;
        resolved.counts[i] = 0;
    }
    if (kallsyms_on_each_symbol(collect, &resolved)) return -OBS_ENODEV;
    /* Independently bind the scan to the KP runtime's lookup entry point. */
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i)
        if (resolved.counts[i] != 1U ||
            kallsyms_lookup_name(obs_symbols[i].name) != resolved.addresses[i])
            return -OBS_ENODEV;
    result = obs_initialize(&io, args);
    if (!result) initialized = 1;
    return result;
}

static long ctl0(const char *args, char *__user output, int output_length)
{
    (void)output; (void)output_length;
    if (!initialized) return -OBS_ENODEV;
    return obs_snapshot(&io, args);
}

static long exit_module(void *reserved)
{
    (void)reserved;
    initialized = 0;
    return 0;
}

KPM_INIT(init);
KPM_CTL0(ctl0);
KPM_EXIT(exit_module);

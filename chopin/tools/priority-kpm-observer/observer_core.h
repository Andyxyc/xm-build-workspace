/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef CHOPIN_PRIORITY_OBSERVER_CORE_H
#define CHOPIN_PRIORITY_OBSERVER_CORE_H
#include "profile.h"

/* Explicit errno constants keep host fixtures independent of kernel headers. */
#define OBS_EINVAL 22
#define OBS_ENODEV 19
#define OBS_EAGAIN 11
#define OBS_EPROTO 71

struct obs_io {
    void *context;
    /* Exact, unique full-name lookup; zero for missing or duplicate. */
    unsigned long (*resolve)(void *context, unsigned int symbol_index);
    /* Called only after all addresses/bounds have passed validation. */
    unsigned long (*read_slot)(void *context, unsigned long address, unsigned int width);
    unsigned char (*read_text)(void *context, unsigned long address);
};

static int obs_equal(const char *a, const char *b)
{
    unsigned int i = 0;
    if (!a || !b) return 0;
    while (a[i] && b[i] && a[i] == b[i]) ++i;
    return a[i] == b[i];
}

static int obs_addresses(const struct obs_io *io, unsigned long addr[OBS_SYMBOL_COUNT])
{
    unsigned int i, j;
    unsigned long base;
    if (!io || !io->resolve || !io->read_text || !io->read_slot) return -OBS_EINVAL;
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) {
        addr[i] = io->resolve(io->context, i);
        if (!addr[i]) return -OBS_ENODEV;
    }
    base = addr[0];
    /* This fixture is exclusively the shipped ARM64 high-half 4.14 kernel. */
    if ((base >> 48) != 0xffffUL || (base & 0xfffUL)) return -OBS_ENODEV;
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) {
        if (base > ~0UL - obs_symbols[i].offset ||
            addr[i] != base + obs_symbols[i].offset) return -OBS_ENODEV;
    }
    if (!(base < addr[1] && addr[1] < addr[2] && addr[2] <= addr[3])) return -OBS_ENODEV;
    for (i = 0; i < OBS_SLOT_COUNT; ++i) {
        unsigned long p = addr[OBS_SLOT_FIRST+i];
        unsigned long w = obs_widths[i];
        if ((p & (w-1)) || p < addr[1] || p > addr[2]-w) return -OBS_ENODEV;
    }
    /* No BSS slot has been read yet. Text fingerprints are finite, not a hash. */
    for (i = 0; i < OBS_ANCHOR_COUNT; ++i) {
        unsigned long p = addr[OBS_ANCHOR_FIRST+i];
        if ((p & 3UL) || p < base || p > addr[1]-32UL) return -OBS_ENODEV;
        for (j = 0; j < 32; ++j)
            if (io->read_text(io->context, p+j) != obs_anchors[i][j]) return -OBS_ENODEV;
    }
    return 0;
}

static long obs_initialize(const struct obs_io *io, const char *args)
{
    unsigned long addresses[OBS_SYMBOL_COUNT];
    if (!obs_equal(args, OBS_INIT_ARGS)) return -OBS_EINVAL;
    return obs_addresses(io, addresses);
}

static long obs_snapshot(const struct obs_io *io, const char *command)
{
    unsigned long addresses[OBS_SYMBOL_COUNT], first[OBS_SLOT_COUNT], second[OBS_SLOT_COUNT];
    unsigned long bits = 0;
    unsigned int i;
    int err;
    if (!obs_equal(command, "snapshot")) return -OBS_EINVAL;
    err = obs_addresses(io, addresses);
    if (err) return err;
    for (i = 0; i < OBS_SLOT_COUNT; ++i)
        first[i] = io->read_slot(io->context, addresses[OBS_SLOT_FIRST+i], obs_widths[i]);
    for (i = 0; i < OBS_SLOT_COUNT; ++i)
        second[i] = io->read_slot(io->context, addresses[OBS_SLOT_FIRST+i], obs_widths[i]);
    for (i = 0; i < OBS_SLOT_COUNT; ++i)
        if (first[i] != second[i]) return -OBS_EAGAIN;
    if (second[2] > 1UL || second[3] > 1UL) return -OBS_EPROTO;
    for (i = 0; i < OBS_SLOT_COUNT; ++i)
        if (second[i] == 0) bits |= 1UL << i;
    /* No raw pointer, UID, string or bitmap content escapes this API. */
    return (long)(OBS_PROTOCOL_BASE | bits);
}
#endif

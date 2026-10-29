/* SPDX-License-Identifier: GPL-2.0-only
 * Memory-only fixture: include the real module/core, never touch a kernel.
 * Skip scdefs' kernel typedefs; use actual pinned kpmodule/kallsyms declarations.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define _KP_UAPI_SCDEF_H_
#include "../priority_observer.c"

unsigned long (*kallsyms_lookup_name)(const char *name);
int (*kallsyms_on_each_symbol)(int (*fn)(void *, const char *, struct module *, unsigned long), void *data);

struct fixture {
    unsigned long addr[OBS_SYMBOL_COUNT];
    unsigned long slots[2][OBS_SLOT_COUNT];
    unsigned int slot_reads, text_reads;
    int corrupt_anchor;
};

static unsigned long fixture_resolve(void *p, unsigned int i)
{
    return ((struct fixture *)p)->addr[i];
}
static unsigned char fixture_text(void *p, unsigned long address)
{
    struct fixture *f = p;
    unsigned int i;
    ++f->text_reads;
    for (i = 0; i < OBS_ANCHOR_COUNT; ++i) {
        unsigned long start = f->addr[OBS_ANCHOR_FIRST+i];
        if (address >= start && address < start+32)
            return obs_anchors[i][address-start] ^ (f->corrupt_anchor == (int)i+1 ? 1 : 0);
    }
    assert(!"unexpected text read");
    return 0;
}
static unsigned long fixture_slot(void *p, unsigned long address, unsigned int width)
{
    struct fixture *f = p;
    unsigned int i = f->slot_reads % OBS_SLOT_COUNT;
    unsigned int round = f->slot_reads / OBS_SLOT_COUNT;
    assert(round < 2);
    assert(address == f->addr[OBS_SLOT_FIRST+i]);
    assert(width == obs_widths[i]);
    ++f->slot_reads;
    return f->slots[round][i];
}
static void reset(struct fixture *f, struct obs_io *io)
{
    unsigned int i;
    memset(f, 0, sizeof(*f));
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i)
        f->addr[i] = 0xffffff8008080000UL + obs_symbols[i].offset;
    io->context = f; io->resolve = fixture_resolve;
    io->read_slot = fixture_slot; io->read_text = fixture_text;
}
static void values(struct fixture *f, unsigned long a, unsigned long b, unsigned long c, unsigned long d)
{
    unsigned long v[4] = {a, b, c, d};
    memcpy(f->slots[0], v, sizeof(v));
    memcpy(f->slots[1], v, sizeof(v));
}
static int empty_scan(int (*cb)(void *, const char *, struct module *, unsigned long), void *p)
{
    (void)cb; (void)p; return 0;
}
static unsigned long no_lookup(const char *name) { (void)name; return 0; }

int main(void)
{
    struct fixture f;
    struct obs_io io;
    unsigned int i, combination;
    unsigned long before[2][OBS_SLOT_COUNT];
    unsigned long v8 = 0x1122334455667788UL;
    unsigned int v4 = 0xaabbccddU;
    unsigned char v1 = 0xa5U;
    unsigned int checks = 0;
#define CHECK(x) do { assert(x); ++checks; } while (0)

    reset(&f, &io);
    CHECK(obs_initialize(&io, OBS_INIT_ARGS) == 0);
    CHECK(f.slot_reads == 0); /* load is not the state observation */
    CHECK(obs_snapshot(&io, "snapshot") == (long)(OBS_PROTOCOL_BASE|15UL));
    CHECK(f.slot_reads == 8);

    /* All 16 observable combinations, with deliberately invalid pointed values.
     * If the core follows either pointer the fixture would abort/fault. */
    for (combination = 0; combination < 16; ++combination) {
        reset(&f, &io);
        values(&f, combination & 1 ? 0 : 1UL,
               combination & 2 ? 0 : ~0UL,
               combination & 4 ? 0 : 1,
               combination & 8 ? 0 : 1);
        memcpy(before, f.slots, sizeof(before));
        CHECK(obs_snapshot(&io, "snapshot") == (long)(OBS_PROTOCOL_BASE|combination));
        CHECK(memcmp(before, f.slots, sizeof(before)) == 0);
        CHECK(f.slot_reads == 8);
    }
    /* Every missing and offset-mismatched identity rejects before any slot read. */
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) {
        reset(&f, &io); f.addr[i] = 0;
        CHECK(obs_snapshot(&io, "snapshot") == -OBS_ENODEV);
        CHECK(f.slot_reads == 0);
        reset(&f, &io); ++f.addr[i];
        CHECK(obs_snapshot(&io, "snapshot") == -OBS_ENODEV);
        CHECK(f.slot_reads == 0);
    }
    for (i = 0; i < OBS_ANCHOR_COUNT; ++i) {
        reset(&f, &io); f.corrupt_anchor = (int)i+1;
        CHECK(obs_snapshot(&io, "snapshot") == -OBS_ENODEV);
        CHECK(f.slot_reads == 0);
    }
    reset(&f, &io);
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) f.addr[i] -= 0xffffff8000000000UL;
    CHECK(obs_snapshot(&io, "snapshot") == -OBS_ENODEV);
    CHECK(f.slot_reads == 0);
    reset(&f, &io);
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i)
        f.addr[i] = 0xfffffffffffff000UL+obs_symbols[i].offset;
    CHECK(obs_snapshot(&io, "snapshot") == -OBS_ENODEV);
    CHECK(f.slot_reads == 0);
    /* Valid page-aligned slide is accepted; absolute base is not falsely pinned. */
    reset(&f, &io);
    for (i = 0; i < OBS_SYMBOL_COUNT; ++i) f.addr[i] += 0x200000UL;
    CHECK(obs_snapshot(&io, "snapshot") == (long)(OBS_PROTOCOL_BASE|15UL));
    for (i = 0; i < OBS_SLOT_COUNT; ++i) {
        reset(&f, &io); f.slots[1][i] = 1;
        CHECK(obs_snapshot(&io, "snapshot") == -OBS_EAGAIN);
    }
    reset(&f, &io); values(&f, 0, 0, 2, 0);
    CHECK(obs_snapshot(&io, "snapshot") == -OBS_EPROTO);
    reset(&f, &io); values(&f, 0, 0, 0, 255);
    CHECK(obs_snapshot(&io, "snapshot") == -OBS_EPROTO);
    reset(&f, &io);
    CHECK(obs_snapshot(&io, "Snapshot") == -OBS_EINVAL);
    CHECK(obs_snapshot(&io, "snapshot ") == -OBS_EINVAL);
    CHECK(obs_snapshot(&io, 0) == -OBS_EINVAL);
    CHECK(obs_initialize(&io, "raw-sha256=wrong") == -OBS_EINVAL);
    CHECK(obs_initialize(&io, 0) == -OBS_EINVAL);
    CHECK(f.slot_reads == 0 && f.text_reads == 0);
    CHECK(obs_snapshot(0, "snapshot") == -OBS_EINVAL);

    /* Actual wrapper code: exact-name collection, duplicate rejection, args,
     * uninitialized control, and acquire loads of local host scalar objects. */
    memset(&resolved, 0, sizeof(resolved));
    collect(&resolved, "is_uid_filter_set_before", 0, 7);
    CHECK(resolve(&resolved, 7) == 0);
    collect(&resolved, obs_symbols[7].name, 0, 8);
    CHECK(resolve(&resolved, 7) == 8);
    collect(&resolved, obs_symbols[7].name, 0, 9);
    CHECK(resolve(&resolved, 7) == 0);
    collect(&resolved, obs_symbols[7].name, 0, 10);
    CHECK(resolve(&resolved, 7) == 0 && resolved.counts[7] == 2);
    CHECK(init("bad", 0, 0) == -OBS_EINVAL);
    CHECK(init(OBS_INIT_ARGS, 0, 0) == -OBS_EINVAL);
    kallsyms_on_each_symbol = empty_scan; kallsyms_lookup_name = no_lookup;
    CHECK(init(OBS_INIT_ARGS, 0, 0) == -OBS_ENODEV);
    CHECK(ctl0("snapshot", 0, 0) == -OBS_ENODEV);
    CHECK(read_slot(0, (unsigned long)&v8, 8) == v8);
    CHECK(read_slot(0, (unsigned long)&v4, 4) == v4);
    CHECK(read_slot(0, (unsigned long)&v1, 1) == v1);
    CHECK(v8 == 0x1122334455667788UL && v4 == 0xaabbccddU && v1 == 0xa5U);
    CHECK(exit_module(0) == 0 && initialized == 0);
    printf("{\"status\":\"PASS\",\"checks\":%u,\"scope\":\"real C core and wrapper memory-only; not device\"}\n", checks);
    return 0;
}

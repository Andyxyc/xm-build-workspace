/* SPDX-License-Identifier: GPL-2.0 */
#ifndef CHOPIN_CPU_IDENTITY_414_H
#define CHOPIN_CPU_IDENTITY_414_H
#include <linux/types.h>
struct chopin_cpu_identity {
    u32 midr;
    u32 bogomips; /* hundredths, matching the official manager command */
    u64 hwcap;
    u64 hwcap2;
};
#ifdef CONFIG_KSU
bool ksu_cpu_identity_get(unsigned int cpu, struct chopin_cpu_identity *out);
u32 ksu_cpu_identity_midr(unsigned int cpu, u32 real_midr);
#else
static inline bool ksu_cpu_identity_get(unsigned int cpu,
                                      struct chopin_cpu_identity *out)
{ return false; }
static inline u32 ksu_cpu_identity_midr(unsigned int cpu, u32 real_midr)
{ return real_midr; }
#endif
#endif

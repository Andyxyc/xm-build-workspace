// SPDX-License-Identifier: GPL-2.0
/* ARM64 4.14 identity reporting, with the official extension IO ABI.
 * Keep the real cpu_data, instruction capabilities, delay calibration,
 * mitigation flags and timer/vDSO state intact. No hardware tuning.
 */
#include <linux/chopin_cpu_identity.h>
#include <linux/cpumask.h>
#include <linux/seqlock.h>
#include <linux/uaccess.h>

static DEFINE_SEQLOCK(chopin_cpuid_lock);
static struct chopin_cpu_identity chopin_cpuid_values[NR_CPUS];
static bool chopin_cpuid_enabled[NR_CPUS];

bool ksu_cpu_identity_get(unsigned int cpu, struct chopin_cpu_identity *out)
{
    unsigned int seq;
    bool enabled;
    if (cpu >= NR_CPUS || !out)
        return false;
    do {
        seq = read_seqbegin(&chopin_cpuid_lock);
        enabled = chopin_cpuid_enabled[cpu];
        *out = chopin_cpuid_values[cpu];
    } while (read_seqretry(&chopin_cpuid_lock, seq));
    return enabled;
}

u32 ksu_cpu_identity_midr(unsigned int cpu, u32 real_midr)
{
    struct chopin_cpu_identity identity;
    return ksu_cpu_identity_get(cpu, &identity) ? identity.midr : real_midr;
}

static int set_spoof_cpu(const struct ksu_set_spoof_cpu_cmd *cmd)
{
    struct chopin_cpu_identity identity;
    unsigned long flags;
    if (cmd->cpu_index >= nr_cpu_ids || !cpu_possible(cmd->cpu_index))
        return -EINVAL;
    /* Zero MIDR explicitly restores the real identity for this CPU. */
    if (cmd->midr && ((cmd->midr >> 16) & 0xf) != 0xf)
        return -EINVAL;
    /* This 4.14 ABI has no AArch64 HWCAP2 names or AT_HWCAP2. */
    if (cmd->hwcap2)
        return -EOPNOTSUPP;
    identity.midr = cmd->midr;
    identity.bogomips = cmd->bogomips;
    identity.hwcap = cmd->hwcap;
    identity.hwcap2 = 0;
    write_seqlock_irqsave(&chopin_cpuid_lock, flags);
    chopin_cpuid_values[cmd->cpu_index] = identity;
    chopin_cpuid_enabled[cmd->cpu_index] = cmd->midr != 0;
    write_sequnlock_irqrestore(&chopin_cpuid_lock, flags);
    return 0;
}

int ksu_extension_cpu_spoof_io(u32 id, void __user *raw)
{
    struct ksu_set_spoof_cpu_cmd cmd;
    (void)id;
    BUILD_BUG_ON(sizeof(cmd) != 32);
    if (!raw || copy_from_user(&cmd, raw, sizeof(cmd)))
        return -EFAULT;
    return set_spoof_cpu(&cmd);
}

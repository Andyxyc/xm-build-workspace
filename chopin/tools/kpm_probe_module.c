/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Task-owned KPM probe. No kernel hooks, polling, or persistent state. */
#include <compiler.h>
#include <kpmodule.h>
#include <linux/printk.h>
#include <linux/string.h>
KPM_NAME("chopin_kpm_probe");
KPM_VERSION("1.0.0");
KPM_LICENSE("GPL v2");
KPM_AUTHOR("chopin port validation");
KPM_DESCRIPTION("Load/control/unload validation only; no hooks");
static long probe_init(const char *args, const char *event, void *__user reserved)
{
    pr_info("chopin_kpm_probe: init\n");
    return 0;
}
static long probe_control(const char *args, char *__user out, int outlen)
{
    return args && !strcmp(args, "ping") ? 0x1357 : -22;
}
static long probe_exit(void *__user reserved)
{
    pr_info("chopin_kpm_probe: exit\n");
    return 0;
}
KPM_INIT(probe_init);
KPM_CTL0(probe_control);
KPM_EXIT(probe_exit);

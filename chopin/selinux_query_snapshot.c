/* SPDX-License-Identifier: GPL-2.0-only */
/* Original-policy query view for this vendor's state-based SELinux server. */
#include "ss/sidtab.h"
#include <linux/vmalloc.h>

struct chopin_original_policy {
    struct selinux_state state;
    struct selinux_ss server;
};
static struct chopin_original_policy *chopin_original_policy;
static DEFINE_MUTEX(chopin_policy_snapshot_mutex);
static bool chopin_policy_snapshot_attempted;
static bool chopin_selinux_hide_enabled = true;

/* Allocate and parse before the legacy policy write lock or stop_machine. */
static noinline int chopin_selinux_capture_original(void)
{
    struct chopin_original_policy *snapshot = NULL;
    struct policy_file file;
    void *bytes = NULL;
    size_t length = 0;
    bool parsed = false, sidtab_ready = false;
    u16 map_size;
    int error = 0;

    mutex_lock(&chopin_policy_snapshot_mutex);
    if (chopin_policy_snapshot_attempted) {
        error = chopin_original_policy ? 0 : -ENODATA;
        goto done;
    }
    chopin_policy_snapshot_attempted = true;
    error = security_read_policy(&selinux_state, &bytes, &length);
    if (error)
        goto fail;
    if (!length || length > 64U * 1024U * 1024U) {
        error = -EOVERFLOW;
        goto fail;
    }
    snapshot = kzalloc(sizeof(*snapshot), GFP_KERNEL);
    if (!snapshot) {
        error = -ENOMEM;
        goto fail;
    }
    snapshot->server.sidtab = kzalloc(sizeof(*snapshot->server.sidtab), GFP_KERNEL);
    if (!snapshot->server.sidtab) {
        error = -ENOMEM;
        goto fail;
    }
    file.data = bytes;
    file.len = length;
    error = policydb_read(&snapshot->server.policydb, &file);
    if (error) /* policydb_read destroys its partial policy on failure. */
        goto fail;
    parsed = true;
    snapshot->server.policydb.len = length;
    error = policydb_load_isids(&snapshot->server.policydb, snapshot->server.sidtab);
    if (error) /* policydb_load_isids destroys its partial SID table. */
        goto fail;
    sidtab_ready = true;
    rwlock_init(&snapshot->server.policy_rwlock);
    mutex_init(&snapshot->server.status_lock);

    read_lock(&selinux_state.ss->policy_rwlock);
    map_size = selinux_state.ss->map.size;
    read_unlock(&selinux_state.ss->policy_rwlock);
    snapshot->server.map.mapping = kmalloc_array(map_size,
        sizeof(*snapshot->server.map.mapping), GFP_KERNEL);
    if (!snapshot->server.map.mapping) {
        error = -ENOMEM;
        goto fail;
    }
    read_lock(&selinux_state.ss->policy_rwlock);
    if (map_size != selinux_state.ss->map.size) {
        read_unlock(&selinux_state.ss->policy_rwlock);
        error = -EAGAIN;
        goto fail;
    }
    snapshot->state = selinux_state;
    snapshot->server.latest_granting = selinux_state.ss->latest_granting;
    snapshot->server.map.size = map_size;
    memcpy(snapshot->server.map.mapping, selinux_state.ss->map.mapping,
           map_size * sizeof(*snapshot->server.map.mapping));
    read_unlock(&selinux_state.ss->policy_rwlock);
    snapshot->state.ss = &snapshot->server;
    /* Query SIDs belong to this independent table; live enforcement is untouched. */
    smp_store_release(&chopin_original_policy, snapshot);
    vfree(bytes);
    pr_info("chopin selinux: original policy query snapshot ready (%zu bytes)\n", length);
    goto done;
fail:
    if (snapshot) {
        if (sidtab_ready)
            sidtab_destroy(snapshot->server.sidtab);
        if (parsed)
            policydb_destroy(&snapshot->server.policydb);
        kfree(snapshot->server.map.mapping);
        kfree(snapshot->server.sidtab);
        kfree(snapshot);
    }
    vfree(bytes);
    pr_err("chopin selinux: original snapshot failed: %d; query hiding inactive\n", error);
done:
    mutex_unlock(&chopin_policy_snapshot_mutex);
    return error;
}

/* Called only by selinuxfs query operations, never by an enforcement hook. */
struct selinux_state *chopin_selinux_query_state(struct selinux_state *live)
{
    struct chopin_original_policy *snapshot;
    if (!READ_ONCE(chopin_selinux_hide_enabled) ||
        current_uid().val % 100000 < 10000 || susfs_is_current_ksu_domain())
        return live;
    snapshot = smp_load_acquire(&chopin_original_policy);
    return snapshot ? &snapshot->state : live;
}

static int chopin_selinux_hide_get(u64 *value)
{
    *value = smp_load_acquire(&chopin_original_policy) &&
             READ_ONCE(chopin_selinux_hide_enabled);
    return 0;
}

static int chopin_selinux_hide_set(u64 value)
{
    if (value > 1)
        return -EINVAL;
    if (value && !smp_load_acquire(&chopin_original_policy))
        return -ENODATA;
    WRITE_ONCE(chopin_selinux_hide_enabled, value != 0);
    return 0;
}

static const struct ksu_feature_handler chopin_selinux_hide_feature = {
    .feature_id = KSU_FEATURE_SELINUX_HIDE,
    .name = "selinux_hide",
    .get_handler = chopin_selinux_hide_get,
    .set_handler = chopin_selinux_hide_set,
};

static void __init chopin_selinux_hide_init(void)
{
    int error = ksu_register_feature_handler(&chopin_selinux_hide_feature);
    if (error)
        pr_err("chopin selinux: feature registration failed: %d\n", error);
}

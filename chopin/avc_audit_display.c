/* SPDX-License-Identifier: GPL-2.0-only */
/* Manual audit-render hook for the pinned chopin SELinux ABI. */
#define CHOPIN_AVC_SPOOF_SUPPORTED 1
static bool chopin_avc_enabled = true;
static bool chopin_avc_ready;
static u32 chopin_avc_ksu_sid;
static u32 chopin_avc_su_sid;
static u32 chopin_avc_priv_app_sid;

/* The caller substitutes only sad.tsid, after the AVC decision is complete. */
u32 chopin_avc_audit_tsid(u32 tsid)
{
    if (!smp_load_acquire(&chopin_avc_ready) || !READ_ONCE(chopin_avc_enabled))
        return tsid;
    if (tsid == READ_ONCE(chopin_avc_ksu_sid) ||
        (READ_ONCE(chopin_avc_su_sid) && tsid == READ_ONCE(chopin_avc_su_sid)))
        return READ_ONCE(chopin_avc_priv_app_sid);
    return tsid;
}

static void chopin_avc_resolve_sids(void)
{
    u32 ksu = 0, su = 0, app = 0;
    int error;

    error = security_secctx_to_secid("u:r:ksu:s0", sizeof("u:r:ksu:s0") - 1, &ksu);
    if (!error)
        error = security_secctx_to_secid("u:r:priv_app:s0:c512,c768",
                  sizeof("u:r:priv_app:s0:c512,c768") - 1, &app);
    if (error || !ksu || !app) {
        pr_err("chopin avc: SID resolution failed: %d; display hook inactive\n", error);
        return;
    }
    /* This ROM can have only ksu; a missing optional su domain is not SID zero. */
    if (security_secctx_to_secid("u:r:su:s0", sizeof("u:r:su:s0") - 1, &su))
        su = 0;
    WRITE_ONCE(chopin_avc_ksu_sid, ksu);
    WRITE_ONCE(chopin_avc_su_sid, su);
    WRITE_ONCE(chopin_avc_priv_app_sid, app);
    smp_store_release(&chopin_avc_ready, true);
}

static int chopin_avc_feature_get(u64 *value)
{
    *value = smp_load_acquire(&chopin_avc_ready) && READ_ONCE(chopin_avc_enabled);
    return 0;
}

static int chopin_avc_feature_set(u64 value)
{
    if (value > 1)
        return -EINVAL;
    if (value && !smp_load_acquire(&chopin_avc_ready))
        return -EAGAIN;
    WRITE_ONCE(chopin_avc_enabled, value != 0);
    return 0;
}

static const struct ksu_feature_handler chopin_avc_feature = {
    .feature_id = KSU_FEATURE_AVC_SPOOF,
    .name = "avc_spoof",
    .get_handler = chopin_avc_feature_get,
    .set_handler = chopin_avc_feature_set,
};

static void __init chopin_avc_feature_init(void)
{
    int error = ksu_register_feature_handler(&chopin_avc_feature);
    if (error)
        pr_err("chopin avc: feature registration failed: %d\n", error);
}

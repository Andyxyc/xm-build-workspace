#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Port *functional* 7SU stealth GET/SET and persistent kernel flag to 3.3.1.

The real ioctl is only available to kernel-trusted manager or root. No fake UI.
Legacy data location is preserved so previously enabled stealth is detectable.
Never change the existing 3.3.1 UAPI 5 version or EVENT_SERVICES semantics.
"""
from pathlib import Path
import shutil
import sys

def once(t,a,b):
    if t.count(a)!=1:raise ValueError(f"expected 1 match found {t.count(a)}: {a[:95]}")
    return t.replace(a,b,1)

def port(new,old):
    new=Path(new).resolve(strict=True);old=Path(old).resolve(strict=True)
    # Old stealth engine is GPL2 and independent of old core. Only copy needed
    # custom files, NOT the old setuid/credential/tracker implementation.
    for rel in ("kernel/manager/stealth.c","kernel/manager/stealth.h"):
        source=old/rel;dst=new/rel
        if dst.exists():raise ValueError("Already ported "+rel)
        if not source.exists():raise FileNotFoundError(source)
        shutil.copy2(source,dst)
    stealth=new/"kernel/manager/stealth.c"
    c=stealth.read_text()
    c=once(c,'O_WRONLY | O_CREAT | O_TRUNC, 0644','O_WRONLY | O_CREAT | O_TRUNC, 0600')
    c=once(c,
      '''    if (kernel_write(fp, data, len, &off) != (ssize_t)len)
        pr_warn("stealth: short write to %s\\n", KSU_STEALTH_PATH);

    filp_close(fp, NULL);
    revert_creds(saved);
    return 0;''',
      '''    ssize_t written = kernel_write(fp, data, len, &off);
    if (written != (ssize_t)len) {
        pr_warn("stealth: write to persistent flag failed (%zd)\\n", written);
        filp_close(fp, NULL);
        revert_creds(saved);
        return written < 0 ? (int)written : -EIO;
    }
    filp_close(fp, NULL);
    revert_creds(saved);
    return 0;''')
    c=once(c,"    fp = filp_open(KSU_STEALTH_PATH, O_RDONLY, 0);",
       "    const struct cred *saved = override_creds(ksu_cred);\n    fp = filp_open(KSU_STEALTH_PATH, O_RDONLY, 0);")
    c=once(c,
       """    if (IS_ERR(fp)) {
        /* 文件不存在 = 默认关闭 */
        ksu_stealth_enabled = false;
        return;
    }""",
       """    if (IS_ERR(fp)) {
        /* Missing flag is normal: default off */
        ksu_stealth_enabled = false;
        revert_creds(saved);
        return;
    }""")
    c=once(c,
      "    filp_close(fp, NULL);\n\n    pr_info(\"stealth: loaded",
      "    filp_close(fp, NULL);\n    revert_creds(saved);\n\n    pr_info(\"stealth: loaded")
    stealth.write_text(c)

    kbuild=new/"kernel/Kbuild";s=kbuild.read_text()
    s=once(s,"kernelsu-objs += manager/apk_sign.o",
      "kernelsu-objs += manager/stealth.o\nkernelsu-objs += manager/apk_sign.o")
    kbuild.write_text(s)

    uapi=new/"uapi/supercall.h";s=uapi.read_text()
    s=once(s,"#endif\n",
        """/* 7SU stealth extension: UAPI version remains 5 for 3.3.1 compatibility.
 * GET/SET explicitly checked for ENOTTY on unsupported kernels. */
struct ksu_stealth_cmd {
    __u8 enabled;
};
static const __u32 KSU_IOCTL_STEALTH_GET = _IOR('K', 25, struct ksu_stealth_cmd);
static const __u32 KSU_IOCTL_STEALTH_SET = _IOW('K', 26, struct ksu_stealth_cmd);
#endif
""")
    uapi.write_text(s)

    dispatch=new/"kernel/supercall/dispatch.c";s=dispatch.read_text()
    s=once(s,'#include "manager/manager_identity.h"',
        '#include "manager/manager_identity.h"\n#include "manager/stealth.h"')
    # Mask only the manager *indicator*, not the actual kernel permission.
    s=s.replace("if (is_manager()) {\n        cmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n    }",
                "if (is_manager() && !ksu_stealth_is_enabled()) {\n        cmd.flags |= KSU_GET_INFO_FLAG_MANAGER;\n    }")
    if s.count("is_manager() && !ksu_stealth_is_enabled()")!=2:
        raise ValueError("both GET_INFO variants were not updated")
    s=once(s,
         "        // Reset for emulated soft reboot\n        services_started = false;",
         "        // Reset for emulated soft reboot\n        services_started = false;\n        ksu_stealth_load();")
    before="// IOCTL handlers mapping table"
    addon="""/* 7SU stealth: only the signed manager or root may query/change state. */
static int do_moksu_stealth_get(void __user *arg)
{
    struct ksu_stealth_cmd cmd = { 0 };
    cmd.enabled = ksu_stealth_is_enabled() ? 1 : 0;
    if (copy_to_user(arg, &cmd, sizeof(cmd)))
        return -EFAULT;
    return 0;
}

static int do_moksu_stealth_set(void __user *arg)
{
    struct ksu_stealth_cmd cmd;
    if (copy_from_user(&cmd, arg, sizeof(cmd)))
        return -EFAULT;
    if (cmd.enabled > 1)
        return -EINVAL;
    return ksu_stealth_set(cmd.enabled == 1);
}

"""
    s=once(s,before,addon+before)
    sentinel="""    {
        .cmd = 0,
        .name = NULL,
        .handler = NULL,
        .perm_check = NULL
    } // Sentinel"""
    insert="""    {
        .cmd = KSU_IOCTL_STEALTH_GET,
        .name = "MOKSU_STEALTH_GET",
        .handler = do_moksu_stealth_get,
        .perm_check = manager_or_root
    },
    {
        .cmd = KSU_IOCTL_STEALTH_SET,
        .name = "MOKSU_STEALTH_SET",
        .handler = do_moksu_stealth_set,
        .perm_check = manager_or_root
    },
"""
    s=once(s,sentinel,insert+sentinel)
    dispatch.write_text(s)

    cpp=new/"manager/app/src/main/cpp/ksu.cc";s=cpp.read_text()
    s+="""

/* KernelSU v3.3.1 + 7SU stealth. A missing ioctl fails closed. */
int moksu_stealth_get()
{
    struct ksu_stealth_cmd cmd = {};
    if (ksuctl(KSU_IOCTL_STEALTH_GET, &cmd) != 0)
        return -1;
    return cmd.enabled == 1 ? 1 : 0;
}

bool moksu_stealth_set(bool enabled)
{
    struct ksu_stealth_cmd cmd = {};
    cmd.enabled = enabled ? 1 : 0;
    if (ksuctl(KSU_IOCTL_STEALTH_SET, &cmd) != 0)
        return false;
    return moksu_stealth_get() == (enabled ? 1 : 0);
}
"""
    cpp.write_text(s)
    h=new/"manager/app/src/main/cpp/ksu.h";s=h.read_text()
    s=once(s,"#endif //KERNELSU_KSU_H",
       "int moksu_stealth_get();\nbool moksu_stealth_set(bool enabled);\n\n#endif //KERNELSU_KSU_H")
    h.write_text(s)
    jni=new/"manager/app/src/main/cpp/jni.cc";s=jni.read_text()
    s+="""

/* JNI query never invents a success on an unsupported kernel. */
extern "C"
JNIEXPORT jint JNICALL
Java_me_weishu_kernelsu_Natives_stealthState(JNIEnv *, jobject)
{
    return moksu_stealth_get();
}

extern "C"
JNIEXPORT jboolean JNICALL
Java_me_weishu_kernelsu_Natives_stealthSet(JNIEnv *, jobject, jboolean enabled)
{
    return moksu_stealth_set(enabled == JNI_TRUE) ? JNI_TRUE : JNI_FALSE;
}
"""
    jni.write_text(s)
    kt=new/"manager/app/src/main/java/me/weishu/kernelsu/Natives.kt"
    s=kt.read_text()
    s=once(s,"    external fun getSuperuserCount(): Int",
       "    external fun stealthState(): Int\n    external fun stealthSet(enabled: Boolean): Boolean\n\n    external fun getSuperuserCount(): Int")
    kt.write_text(s)
    # ksud native webadmin can use the same signed manager or root ioctl.
    rust=new/"userspace/ksud/src/ksucalls.rs"
    s=rust.read_text()
    s+="""

/* 7SU stealth ioctl extension; 3.3.1 base UAPI remains 5. */
pub fn stealth_get_authed() -> anyhow::Result<bool> {
    let mut cmd = ksu_uapi::ksu_stealth_cmd { enabled: 0 };
    ksuctl(ksu_uapi::KSU_IOCTL_STEALTH_GET, &raw mut cmd)?;
    Ok(cmd.enabled != 0)
}
pub fn stealth_set_authed(enabled: bool) -> anyhow::Result<()> {
    let mut cmd = ksu_uapi::ksu_stealth_cmd { enabled: u8::from(enabled) };
    ksuctl(ksu_uapi::KSU_IOCTL_STEALTH_SET, &raw mut cmd)?;
    anyhow::ensure!(stealth_get_authed()? == enabled, "stealth write not persisted");
    Ok(())
}
"""
    rust.write_text(s)
    print("MOKSU_7SU_KERNEL_STEALTH_PORTED_TO_KSU331")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: port_stealth.py PINNED_KSU331 LEGACY_7KIMISU")
    port(sys.argv[1],sys.argv[2])

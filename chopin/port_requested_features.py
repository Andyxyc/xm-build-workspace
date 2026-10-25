"""Apply the requested old-kernel identity and genuine ADB-root features.

Run after all r5 ports. Public source only; no device images or private key.
"""
from pathlib import Path
import json,re,sys
root=Path(sys.argv[1]).resolve()
here=Path(__file__).resolve().parent
def replace(name,old,new):
    p=root/name;s=p.read_text();assert s.count(old)==1,(name,old[:90],s.count(old))
    p.write_text(s.replace(old,new,1))

identity=json.loads((here/'stock-identity.json').read_text())
assert identity['release']=='4.14.186-gaa24d707761c'
makefile=(root/'Makefile').read_text()
assert all(re.search(r'^'+key+r' = '+value+r'$',makefile,re.M)
           for key,value in [('VERSION','4'),('PATCHLEVEL','14'),('SUBLEVEL','186')])
# Exact display identity is independent of the real compiler provenance saved
# in release-evidence/clang-version.txt and the immutable source/build receipt.
defines={'UTS_MACHINE':'aarch64','UTS_VERSION':identity['version'],
         'LINUX_COMPILE_BY':identity['compile_by'],
         'LINUX_COMPILE_HOST':identity['compile_host'],
         'LINUX_COMPILER':identity['compiler']}
header='/* Stock display metadata; actual build provenance is recorded separately. */\n'
header+=''.join('#define '+k+' '+json.dumps(v)+'\n' for k,v in defines.items())
script='#!/bin/sh\nset -eu\nTARGET="$1"\ncat > "${TARGET}.tmp" <<\'CHOPIN_STOCK_METADATA\'\n'+header+'CHOPIN_STOCK_METADATA\n'
script+='if cmp -s "${TARGET}.tmp" "$TARGET"; then rm -f "${TARGET}.tmp"; else mv -f "${TARGET}.tmp" "$TARGET"; fi\n'
(root/'scripts/mkcompile_h').write_text(script)
(root/'scripts/setlocalversion').write_text('#!/bin/sh\nprintf \'%s\\n\' \'-gaa24d707761c\'\n')
config=root/'arch/arm64/configs/chopin_user_defconfig';s=config.read_text()
for k,v in [('CONFIG_LOCALVERSION','""'),('CONFIG_LOCALVERSION_AUTO','n'),('CONFIG_KSU_FEATURE_ADBROOT','y')]:
    s=re.sub(r'(?m)^(?:'+k+r'=.*|# '+k+r' is not set)\n','',s)
    s+= ('# '+k+' is not set\n') if v=='n' else k+'='+v+'\n'
config.write_text(s)

# Replace only the incompatible implementation; re-enable the real IO handler.
(root/'include/linux/chopin_cpu_identity.h').write_bytes((here/'cpu_identity_414.h').read_bytes())
(root/'KernelSU/kernel/extension/cpu_spoof.c').write_bytes((here/'cpu_identity_414.c').read_bytes())
replace('KernelSU/kernel/ksu_main.c',
 '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n#include "extension/cpu_spoof.c"\n#endif',
 '#include "extension/cpu_spoof.c"')
p=root/'KernelSU/kernel/extension/extension.c';s=p.read_text()
start=s.index('#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n    static const struct ksu_extension_handler cpu_spoof_handler')
end=s.index('#endif\n',start)
s=s[:start]+s[start:end].split('\n',1)[1]+s[end+len('#endif\n'):]
old='#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n    if (ksu_register_extension_handler(&cpu_spoof_handler))\n        pr_err("extension: failed to register cpu_spoof\\n");\n#endif'
assert s.count(old)==1;s=s.replace(old,old.split('\n',1)[1].rsplit('\n',1)[0],1);p.write_text(s)

name='arch/arm64/kernel/cpuinfo.c'
replace(name,'#include <linux/delay.h>','#include <linux/delay.h>\n#include <linux/chopin_cpu_identity.h>')
replace(name,'\t\tu32 midr = cpuinfo->reg_midr;',
 '\t\tstruct chopin_cpu_identity identity;\n\t\tbool spoof = ksu_cpu_identity_get(i, &identity);\n\t\tu32 midr = spoof ? identity.midr : cpuinfo->reg_midr;')
old='\t\tseq_printf(m, "BogoMIPS\\t: %lu.%02lu\\n",\n\t\t\t   loops_per_jiffy / (500000UL/HZ),\n\t\t\t   loops_per_jiffy / (5000UL/HZ) % 100);'
new='\t\tif (spoof)\n\t\t\tseq_printf(m, "BogoMIPS\\t: %u.%02u\\n", identity.bogomips / 100, identity.bogomips % 100);\n\t\telse {\n'+old+'\n\t\t}'
replace(name,old,new)
replace(name,'if (elf_hwcap & (1 << j))','if ((spoof ? identity.hwcap : elf_hwcap) & (1UL << j))')
replace(name,'CPUREGS_ATTR_RO(midr_el1, midr);', '''static ssize_t midr_el1_show(struct kobject *kobj,
        struct kobj_attribute *attr, char *buf)
{
    struct cpuinfo_arm64 *info = kobj_to_cpuinfo(kobj);
    unsigned int cpu;
    u32 midr = info->reg_midr;
    for_each_possible_cpu(cpu) {
        if (info == &per_cpu(cpu_data, cpu)) {
            midr = ksu_cpu_identity_midr(cpu, midr);
            break;
        }
    }
    return midr ? sprintf(buf, "0x%016x\\n", midr) : 0;
}
static struct kobj_attribute cpuregs_attr_midr_el1 = __ATTR_RO(midr_el1);''')
replace('arch/arm64/kernel/cpufeature.c','#include <linux/smp.h>',
        '#include <linux/smp.h>\n#include <linux/chopin_cpu_identity.h>')
replace('arch/arm64/kernel/cpufeature.c','\tcase SYS_MIDR_EL1:\n\t\t*valp = read_cpuid_id();',
        '\tcase SYS_MIDR_EL1:\n\t\t*valp = ksu_cpu_identity_midr(raw_smp_processor_id(), read_cpuid_id());')

p=root/'KernelSU/kernel/feature/adb_root.c';s=p.read_text()
start=s.index('static long setup_ld_preload(void ***envp_user_ptr)')
end=s.index('static long do_ksu_adb_root_handle_execveat', start)
s=s[:start]+(here/'adb_root_env_414.inc').read_text()+'\n'+s[end:]
s=s.replace('    bool enable = value != 0;', '    bool enable;\n    if (value > 1) return -EINVAL;\n    enable = value != 0;',1)
p.write_text(s)
# Keep the official certificate allowlist and add only this owner's public key.
cert=json.loads((here/'owner-manager-cert.json').read_text())
assert re.fullmatch('[0-9a-f]{64}',cert['certificate_sha256'])
replace('KernelSU/kernel/manager/apk_sign.c','} apk_sign_keys[] = {',
        '} apk_sign_keys[] = {\n    { '+str(cert['certificate_bytes'])+', "'+cert['certificate_sha256']+'" }, /* owner-built manager; private key stays offline */')
print('Applied stock display identity, ARM64 4.14 CPU identity reporting, ADB root and owner manager certificate')

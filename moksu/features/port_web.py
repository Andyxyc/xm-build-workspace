#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Port the actual 7kimisu web administration HTTP server into KernelSU 3.3.1.

Source is pinned to 7kimisu v2.29; no sensitive data, keys, or compiled
third-party binaries are imported. Root HTTP is loopback-only and capability-
URL token authenticated. Do not expose a public bind address.
"""
from pathlib import Path
import shutil
import sys
import re

def one(s,old,new):
    n=s.count(old)
    if n!=1:raise ValueError(f"expected one anchor found {n}: {old[:100]!r}")
    return s.replace(old,new,1)

def port(new_root,old_root):
    new_root=Path(new_root).resolve(strict=True)
    old_root=Path(old_root).resolve(strict=True)
    oldsrc=old_root/"userspace/ksud/src"
    dest=new_root/"userspace/ksud/src"
    for f in ("webadmin.rs","webadmin_ksud.rs","atomic.rs"):
        p=oldsrc/f
        if not p.is_file():raise FileNotFoundError(p)
        dst=dest/f
        if dst.exists():raise ValueError("web restoration already applied: "+str(dst))
        shutil.copy2(p,dst)
    assets=old_root/"userspace/ksud/assets/webadmin"
    root=new_root/"userspace/ksud/assets/webadmin"
    if root.exists():raise ValueError("web UI assets already present")
    shutil.copytree(assets,root)
    # Preserve functionality/security logic, change only recognizable branding.
    index=root/"index.html"
    s=index.read_text()
    s=one(s,'<title>7kimisu 网页管理器</title>','<title>moksu · 心中都是莫｜网页控制台</title>')
    s=one(s,'<h1>7kimisu</h1>','<h1>moksu</h1>')
    s=one(s,'<div class="sub">网页管理器</div>','<div class="sub">心中都是莫 · 安全控制台</div>')
    index.write_text(s)
    style=root/"app.css"
    s=style.read_text()
    s+="""
/* moksu UI refresh | Aurora Night | author 心中都是莫 */
body {
  background:
    radial-gradient(90rem 55rem at -35% -15%, rgba(137,107,255,.10), transparent 70%),
    radial-gradient(65rem 50rem at 125% 65%, rgba(48,222,189,.09), transparent 65%),
    var(--bg);
  background-attachment: fixed;
}
header {
  background: linear-gradient(115deg,rgba(27,28,53,.93),rgba(11,19,33,.95));
  border-bottom: 1px solid rgba(154,134,255,.26);
  box-shadow: 0 6px 36px rgba(3,6,17,.28);
}
.brand .mark {
  box-shadow: 0 0 0 1px rgba(186,165,255,.18), 0 6px 24px rgba(122,93,255,.25);
}
.brand h1 { letter-spacing: -.025em; font-weight: 780; }
.brand .sub { letter-spacing: .06em; }
nav {
  position: sticky; top: 71px; z-index: 4;
  background: color-mix(in srgb,var(--bg) 89%,transparent);
  backdrop-filter: blur(16px);
  padding-block: 9px;
}
nav button { border-radius: 14px; transition: background .18s,color .18s,transform .18s; }
nav button.on {
  background: linear-gradient(135deg,rgba(154,133,255,.18),rgba(42,210,199,.11));
  border-color: rgba(154,133,255,.4);
  color: var(--fg);
}
.card,.mod {
  border-color: color-mix(in srgb,var(--accent) 18%,var(--line));
  border-radius: 20px;
  background: color-mix(in srgb,var(--card) 95%,transparent);
  box-shadow: 0 8px 26px rgba(3,6,18,.19);
}
.chip.on,.btn-primary {
  background: linear-gradient(125deg,var(--accent),#38c9c0);
}
:focus-visible {outline:2px solid var(--accent);outline-offset:3px;}
@media (prefers-reduced-motion:reduce) {
  *,*::before,*::after {animation:none!important;transition:none!important;}
}
"""
    style.write_text(s)
    theme=root/"themes.css"
    s=theme.read_text()+"""
/* moksu — Aurora Night (default 7k theme restyle, not upstream look) */
:root,[data-theme="7k"][data-scheme="dark"] {
  --bg:#0a0f1c;--bg-soft:#11192c;--card:#141e33;--card-2:#1b2940;
  --card-3:#223550;--line:#30405d;--line-soft:rgba(187,198,241,.09);
  --fg:#f3f6ff;--fg-dim:#bcc8db;--fg-mute:#8594b0;
  --accent:#a48cff;--accent-fg:#101322;--ok:#52e3bf;--warn:#f8c77d;
  --bad:#ff829a;--info:#88c6ff;--on-strong:#fff;
  --shadow:0 12px 26px rgba(5,8,20,.33);
}
[data-theme="7k"][data-scheme="light"] {
  --bg:#f5f5fc;--bg-soft:#eef0f9;--card:#fff;--card-2:#f3f1ff;
  --card-3:#ebe7fc;--line:#dbdaf0;--line-soft:rgba(53,48,90,.08);
  --fg:#1b2034;--fg-dim:#55617a;--fg-mute:#78839c;
  --accent:#6954c8;--accent-fg:#fff;--ok:#087b66;--warn:#ad6d08;
  --bad:#c43c65;--info:#386dbb;--on-strong:#fff;
  --shadow:0 12px 26px rgba(46,35,90,.08);
}
"""
    theme.write_text(s)
    # Keep settings/URLs local backwards-compatible with existing sevenk data
    # directory; don't rename configuration storage without an atomic migration.
    web=dest/"webadmin.rs"
    s=web.read_text()
    s=one(s,'pub const SERVICE_NAME: &str = "7kimisu";',
          'pub const SERVICE_NAME: &str = "moksu";')
    # This comment is harmless, but user-facing page and log should use new brand.
    s=s.replace('# 7kimisu 网页管理器', '# moksu · 心中都是莫 网页管理器')
    web.write_text(s)
    # daemon CLI: preserve official parser/cmds, append 7kimisu webadmin subset.
    legacy=(oldsrc/"cli.rs").read_text()
    cli=dest/"cli.rs"
    txt=cli.read_text()
    block=legacy.split("#[derive(clap::Subcommand, Debug)]\nenum Webadmin {",1)
    if len(block)!=2:raise ValueError("missing legacy enum Webadmin")
    enum="#[derive(clap::Subcommand, Debug)]\nenum Webadmin {"+block[1].split("\n#[derive(clap::Subcommand, Debug)]\n",1)[0]+"\n"
    txt=one(txt,"#[derive(clap::Subcommand, Debug)]\nenum Commands {",enum+"\n#[derive(clap::Subcommand, Debug)]\nenum Commands {")
    txt=one(txt,"enum Commands {\n    /// Manage KernelSU modules",
          'enum Commands {\n    /// moksu local, token-protected web administration\n    Webadmin {\n        #[command(subcommand)]\n        command: Webadmin,\n    },\n\n    /// Manage KernelSU modules')
    a=legacy.index("        Commands::Webadmin { command } => match command {")
    b=legacy.index("        Commands::PostFsData =>",a)
    webbranch=legacy[a:b]
    txt=one(txt,"        Commands::PostFsData =>",webbranch+"        Commands::PostFsData =>")
    cli.write_text(txt)
    main=dest/"main.rs";s=main.read_text()
    s=one(s,"mod assets;","mod assets;\nmod webadmin;\n#[cfg(target_os = \"android\")]\nmod webadmin_ksud;\nmod atomic;")
    main.write_text(s)
    init=dest/"init_event.rs";s=init.read_text()
    # Run after ensure_binaries; default config off, no web daemon when disabled.
    s=one(s,
          '    assets::ensure_binaries(true).with_context(|| "Failed to extract bin assets")?;',
          '    assets::ensure_binaries(true).with_context(|| "Failed to extract bin assets")?;\n'
          '    // Enabled only on explicit opt-in. No public bind; 256-bit local URL token.\n'
          '    crate::webadmin_ksud::start_if_enabled();')
    init.write_text(s)
    # audit: grep for expected auth and loopback constructs, fail if missing.
    now=web.read_text()
    assert "TOKEN_BYTES: usize = 32" in now
    assert "Ipv4Addr::LOCALHOST" in now
    assert "MAX_CONNS: usize = 16" in now
    print("MOKSU_7SU_WEB_BACKEND_PORTED",len(now),len((dest/"webadmin_ksud.rs").read_bytes()))

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: port_web.py KSU331_SOURCE LEGACY_7KIMISU_SOURCE")
    port(sys.argv[1],sys.argv[2])

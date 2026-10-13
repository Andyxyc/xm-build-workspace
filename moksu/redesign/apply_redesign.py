#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Moksu v3.3.1 web redesign + permission-path fix, no fake root controls.

Run only after:
  apply_release.py ; port_stealth.py ; port_web.py ;
  port_web_compat.py ; port_android.py
Requires the *matching rebuilt* eight LKM. This intentionally does not try to
rewrite every browser's homepage from an Android package.
"""
from pathlib import Path
import sys

def replace_once(s,old,new,name):
    found=s.count(old)
    if found != 1:
        raise ValueError(f"{name}: expected one occurrence of {old[:90]!r}, found {found}")
    return s.replace(old,new,1)

def patch(root,overlay):
    root=Path(root).resolve(strict=True)
    overlay=Path(overlay).resolve(strict=True)
    assets=root/"userspace/ksud/assets/webadmin"
    oldcss=(assets/"app.css").read_text()
    (assets/"index.html").write_text((overlay/"web/index.html").read_text())
    (assets/"app.css").write_text(oldcss+"\n\n"+(overlay/"web/modern.css").read_text())
    js_path=assets/"app.js"
    js=js_path.read_text()
    js=replace_once(js,'  appFilter: "all",     // all | granted | plain | system',
       '  appFilter: "all",     // all | granted | plain | system', "JS anchor")

    # Direct one-tap grants; don't show success until kernel verifies the result.
    from_here=js.index("function setAppRoot(g, allow) {")
    until=js.index("\n/* ── 单个 App 的 root 配置",from_here)
    js=js[:from_here]+'''function setAppRoot(g, allow) {
  if (state.busy) return;
  state.busy = true;
  toast("正在向内核写入权限…");
  post("/api/app/root", { pkg: g.primary.pkg, uid: g.uid, allow: allow ? "1" : "0" })
    .then(function (r) {
      if (!r.ok) throw new Error(r.error || r.message || "内核未接受配置");
      return get("/api/app/profile", { pkg: g.primary.pkg, uid: g.uid })
        .then(function (v) {
          if (!v.ok || !v.profile || !!v.profile.allowSu !== allow)
            throw new Error("已发送，但内核回读的权限没有改变");
          toast(allow ? "已授予超级用户权限" : "已撤销超级用户权限");
          return loadApps();
        });
    })
    .catch(function (e) { toast("授权失败：" + e.message); loadApps(); })
    .then(function () { state.busy = false; });
}
'''+js[until:]
    # Fix ability to use keyboard on switch and indicate state.
    js=replace_once(js,
      '  sw.setAttribute("role", "switch");\n  sw.title = g.granted ?',
      '  sw.setAttribute("role", "switch");\n  sw.setAttribute("tabindex", "0");\n'
      '  sw.setAttribute("aria-checked", g.granted ? "true" : "false");\n'
      '  sw.title = g.granted ?', "grant switch")
    js=replace_once(js,
      '  acts.appendChild(sw);\n  card.appendChild(acts);\n  return card;',
      '  sw.onkeydown = function(ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); sw.click(); } };\n'
      '  acts.appendChild(sw);\n  card.appendChild(acts);\n  return card;', "user card keyboard")

    # Replace the visual panel with an authentic page for credentials, security,
    # browser homepage instructions, and custom 256-bit access key.
    marker="function renderAbout() {"
    assert js.count(marker)==1
    security=r'''
/* moksu credentials remain local; this UI never sends the key to a remote host.
 * URL keys grant ROOT on this device, so do NOT store secrets in localStorage. */
function renderSecurity() {
  var box=$("#t-security");
  clear(box);
  var token=P.split("/").pop();
  var grid=el("div","security-grid");
  box.appendChild(grid);
  var c=el("div","card");
  c.appendChild(el("div","eyebrow","SECURITY CREDENTIAL"));
  c.appendChild(el("div","security-title","网页访问密钥"));
  c.appendChild(el("div","security-subtitle","只有拥有此密钥的本机浏览器才能管理超级用户与模块"));
  var secret=el("div","secret-value","•••• •••• •••• •••• •••• ••••");
  secret.setAttribute("aria-live","polite");
  var visible=false;
  var line=el("div","secret-line");line.appendChild(secret);
  var reveal=el("button","btn","显示密钥");
  reveal.onclick=function(){
    visible=!visible;
    secret.textContent=visible?token:"•••• •••• •••• •••• •••• ••••";
    reveal.textContent=visible?"隐藏密钥":"显示密钥";
  };
  line.appendChild(reveal);c.appendChild(line);
  var actions=el("div","security-actions");
  var copy=el("button","btn primary","复制密钥");
  copy.onclick=function(){copyText(token,function(){toast("密钥已复制，请勿分享给他人");});};
  actions.appendChild(copy);
  var copyUrl=el("button","btn","复制网页地址");
  copyUrl.onclick=function(){copyText(location.origin+P,function(){toast("网页地址已复制");});};
  actions.appendChild(copyUrl);
  c.appendChild(actions);
  grid.appendChild(c);

  var change=el("div","card");
  change.appendChild(el("div","eyebrow","ACCESS MANAGEMENT"));
  change.appendChild(el("div","security-title","更换专属密钥"));
  change.appendChild(el("p","security-subtitle","可以随机生成，也可以填写 64 位十六进制密钥。更换后旧浏览器标签和书签立即失效。"));
  var field=el("input","security-input");
  field.type="password";
  field.autocomplete="off";
  field.spellcheck=false;
  field.maxLength=64;
  field.placeholder="64 位 0-9 / a-f";
  field.setAttribute("aria-label","新访问密钥");
  change.appendChild(field);
  var buttons=el("div","security-actions");
  var gen=el("button","btn","生成高强度新密钥");
  gen.onclick=function(){
    if(!window.crypto||!window.crypto.getRandomValues){toast("浏览器不支持安全随机数，请使用重置密钥");return;}
    var bytes=new Uint8Array(32);window.crypto.getRandomValues(bytes);
    field.value=Array.from(bytes).map(function(x){return x.toString(16).padStart(2,"0");}).join("");
    field.type="text";toast("已安全生成新密钥，点击保存才会生效");
  };
  var save=el("button","btn primary","保存新密钥");
  save.onclick=function(){
    var k=field.value.trim().toLowerCase();
    if(!/^[0-9a-f]{64}$/.test(k)){toast("密钥必须是 64 位十六进制字符");return;}
    confirmSheet("确定替换密钥？",
       "保存后，所有旧网页链接会立即失效；请妥善保存新的访问地址。",
       "确认更换",function(){
        post("/api/access/change",{token:k}).then(function(r){
          if(!r.ok||!r.url)throw new Error(r.error||"更换失败");
          location.replace(r.url);
        }).catch(function(e){toast("更换失败："+e.message);});
       });
  };
  buttons.appendChild(gen);buttons.appendChild(save);
  var rotate=el("button","btn","随机重置");
  rotate.onclick=function(){
    confirmSheet("重置网页访问密钥？","将使用内核设备安全随机数生成新密钥，旧链接立即失效。",
      "重置",function(){
        post("/api/access/rotate",{}).then(function(r){
          if(!r.ok||!r.url)throw new Error(r.error||"重置失败");
          location.replace(r.url);
        }).catch(function(e){toast("重置失败："+e.message);});
      });
  };
  buttons.appendChild(rotate);
  change.appendChild(buttons);
  grid.appendChild(change);

  var boot=el("div","card wide");
  boot.appendChild(el("div","eyebrow","BROWSER HOMEPAGE"));
  boot.appendChild(el("div","security-title","浏览器启动页"));
  boot.appendChild(el("p","security-subtitle",
    "希望打开浏览器时直接进入 moksu：先复制下方地址，再在所用浏览器的「主页 / 启动页」设置中添加。浏览器是否每次启动载入主页由浏览器决定，moksu 不会擅自劫持其他应用。"));
  var address=el("div","secret-value",location.origin+P);
  boot.appendChild(address);
  var wrap=el("div","security-actions");
  var copyBrowser=el("button","btn primary","复制浏览器启动地址");
  copyBrowser.onclick=function(){copyText(location.origin+P,function(){toast("地址已复制，可粘贴为浏览器主页");});};
  wrap.appendChild(copyBrowser);
  boot.appendChild(wrap);
  grid.appendChild(boot);
}

'''
    js=js.replace(marker,security+marker)
    js=replace_once(js,'c1.appendChild(row("package", "网页管理器", "7kimisu 内置"));',
       'c1.appendChild(row("package", "网页管理器", "moksu · 心中都是莫"));', "about author")
    js=replace_once(js,'  ["status", "users", "modules", "sulog", "about"].forEach(function (t) {',
       '  ["status", "users", "modules", "sulog", "security", "about"].forEach(function (t) {', "tab set")
    js=replace_once(js,'  if (tab === "about") renderAbout();',
       '  if (tab === "security") renderSecurity();\n'
       '  if (tab === "about") renderAbout();', "security tab")
    js=replace_once(js,'  state.tab = tab;',
       '  state.tab = tab;\n'
       '  var titles={status:["运行概览","查看内核状态、运行信息与管理入口"],'
       'users:["超级用户","一键授权和高级权限配置"],'
       'modules:["模块中心","安装、运行及管理功能模块"],'
       'sulog:["授权日志","回看授权和提权请求"],'
       'security:["安全设置","专属访问密钥与浏览器启动入口"],'
       'about:["关于 moksu","版本信息及开源许可"]};\n'
       '  var current=titles[tab]||titles.status;\n'
       '  $("#page-title").textContent=current[0];\n'
       '  $("#page-description").textContent=current[1];\n'
       '  $("#crumb-current").textContent=current[0];', "page headings")
    js=js.replace('localStorage.getItem("7k-webadmin-theme")',
                   'localStorage.getItem("moksu-web-theme") || localStorage.getItem("7k-webadmin-theme")')
    js=js.replace('localStorage.setItem("7k-webadmin-theme", id)',
                  'localStorage.setItem("moksu-web-theme", id)')
    js_path.write_text(js)

    # Kernel: Root daemon is already root but two profile IOCTLs were reserved
    # to the Android manager, causing manager-appid impersonation failures.
    # Extend *only those two* to manager_or_root, not arbitrary ioctl commands.
    perm=root/"kernel/supercall/dispatch.c"
    src=perm.read_text()
    for ioctl in ("KSU_IOCTL_GET_APP_PROFILE","KSU_IOCTL_SET_APP_PROFILE"):
        match='''        .cmd = '''+ioctl+''',
        .name = "'''+('GET_APP_PROFILE' if ioctl.endswith("GET_APP_PROFILE") else 'SET_APP_PROFILE')+'''",
        .handler = '''+('do_get_app_profile' if ioctl.endswith("GET_APP_PROFILE") else 'do_set_app_profile')+''',
        .perm_check = only_manager'''
        src=replace_once(src,match,match.replace("only_manager","manager_or_root"),ioctl+" root-authorized")
    perm.write_text(src)

    # Explicit ioctl with preserved errno. The old fork tried setresuid to
    # the manager UID which fails when hiding is enabled or appid isn't known.
    calls=root/"userspace/ksud/src/ksucalls.rs"
    s=calls.read_text()
    begin=s.index("pub fn get_app_profile(uid: u32, key: &str) ")
    end=s.index("\npub fn read_cstr(",begin)
    replacement=r'''/// Profile IOCTL intended for the trusted root ksud daemon.
/// This requires the matching moksu kernel's manager_or_root permissions.
fn ksuctl_profile<T>(request:u32, arg:*mut T) -> std::io::Result<i32> {
    let fd=*DRIVER_FD.get_or_init(|| init_driver_fd().unwrap_or(-1));
    if fd < 0 {return Err(std::io::Error::other("KernelSU driver not accessible"));}
    let ret=unsafe {libc::ioctl(fd, request as libc::c_int, arg)};
    if ret < 0 {Err(std::io::Error::last_os_error())} else {Ok(ret)}
}

pub fn get_app_profile(uid: u32, key: &str) -> anyhow::Result<Option<ksu_uapi::app_profile>> {
    let mut cmd:ksu_uapi::ksu_get_app_profile_cmd=unsafe {std::mem::zeroed()};
    cmd.profile.version=ksu_uapi::KSU_APP_PROFILE_VER;
    cmd.profile.curr_uid=uid as i32;
    write_cstr(&mut cmd.profile.key[..],key);
    match ksuctl_profile(ksu_uapi::KSU_IOCTL_GET_APP_PROFILE,&raw mut cmd) {
        Ok(_)=>Ok(Some(cmd.profile)),
        Err(e) if e.raw_os_error()==Some(libc::ENOENT)=>Ok(None),
        Err(e)=>Err(anyhow::anyhow!("读取 Root 授权失败: {e}")),
    }
}

pub fn set_app_profile(profile:&ksu_uapi::app_profile)->anyhow::Result<()> {
    let mut cmd:ksu_uapi::ksu_set_app_profile_cmd=unsafe {std::mem::zeroed()};
    cmd.profile=*profile;
    ksuctl_profile(ksu_uapi::KSU_IOCTL_SET_APP_PROFILE,&raw mut cmd)
        .map_err(|e| anyhow::anyhow!("内核写入权限失败: {e}"))?;
    Ok(())
}
'''
    s=s[:begin]+replacement+s[end:]
    calls.write_text(s)
    # New route to show and change an already-authenticated key. Never log it.
    server=root/"userspace/ksud/src/webadmin.rs"
    s=server.read_text()
    route_marker='''        "/api/modules" => respond(&mut writer, 200, JSON, server.backend.modules().to_string().as_bytes()),'''
    new_routes=r'''        "/api/access/change" => {
            require_post!();
            let candidate=params.get("token").cloned().unwrap_or_default().to_lowercase();
            let answer: Result<String,String>=(||{
                if !valid_token(&candidate) {
                    return Err("访问密钥必须是 64 位十六进制字符".to_string());
                }
                // Reject trivially weak repeated patterns. Use random-generated key by default.
                let n=candidate.as_bytes().chunks_exact(2)
                   .map(|p| std::str::from_utf8(p).unwrap_or(""))
                   .collect::<std::collections::HashSet<_>>().len();
                if n < 12 {return Err("此密钥过于简单，请生成强随机密钥".to_string());}
                let mut cfg=Config::load();
                if cfg.token==candidate {return Err("与当前密钥相同".to_string());}
                cfg.token=candidate;
                cfg.save().map_err(|e|format!("保存密钥失败: {e}"))?;
                let port=effective_port().unwrap_or(cfg.bound_port.max(cfg.port));
                Ok(url_with(port,&cfg.token))
            })();
            let body=match answer {
                Ok(url)=>serde_json::json!({"ok":true,"url":url}).to_string(),
                Err(error)=>serde_json::json!({"ok":false,"error":error}).to_string(),
            };
            respond(&mut writer,200,JSON,body.as_bytes())
        }
        "/api/access/rotate" => {
            require_post!();
            let answer=reset_token().map(|t| {
                let cfg=Config::load();
                url_with(effective_port().unwrap_or(cfg.bound_port.max(cfg.port)),&t)
            });
            let body=match answer {
                Ok(url)=>serde_json::json!({"ok":true,"url":url}).to_string(),
                Err(e)=>serde_json::json!({"ok":false,"error":format!("安全随机密钥生成失败: {e}")}).to_string(),
            };
            respond(&mut writer,200,JSON,body.as_bytes())
        }
'''
    s=replace_once(s,route_marker,new_routes+route_marker,"add access routes")
    server.write_text(s)

    # Root toggle confirmation is checked from actual kernel readback.
    daemon=root/"userspace/ksud/src/webadmin_ksud.rs"
    s=daemon.read_text()
    needle='''        ksucalls::set_app_profile(&profile).map_err(|e| format!("写入失败: {e:#}"))?;
        log_line(&format!(
            "超级用户：{} {pkg}(uid={uid})",'''
    replace='''        ksucalls::set_app_profile(&profile).map_err(|e| format!("写入失败: {e:#}"))?;
        let saved=ksucalls::get_app_profile(uid,pkg)
            .map_err(|e|format!("内核回读权限失败: {e:#}"))?;
        if saved.as_ref().map(|p|p.allow_su)!=Some(allow) {
            return Err("内核未保存新授权状态，请检查当前是否已加载匹配的 moksu 模块".to_string());
        }
        log_line(&format!(
            "超级用户：{} {pkg}(uid={uid})",'''
    s=replace_once(s,needle,replace,"verified permissions")
    daemon.write_text(s)

    # Android screen: branding; display/copy auth token only on explicit reveal.
    activity=root/"manager/app/src/main/java/me/weishu/kernelsu/mok/MoksuExtrasActivity.kt"
    s=activity.read_text()
    s=s.replace('Text("7SU 扩展管理",fontSize=21.sp,fontWeight=FontWeight.SemiBold)',
                'Text("专属控制台",fontSize=21.sp,fontWeight=FontWeight.SemiBold)')
    s=s.replace('Text("7SU 隐身 / 隐藏模式",fontSize=18.sp,fontWeight=FontWeight.Bold)',
                'Text("专属隐藏模式",fontSize=18.sp,fontWeight=FontWeight.Bold)')
    s=s.replace('Text("内核隐身",fontSize=14.sp,color=Mint)',
                'Text("隐藏管理状态",fontSize=14.sp,color=Mint)')
    s=s.replace('Text("原版 7SU 隐身仅隐藏管理器 Root 状态显示。入口仍保留，可随时恢复；不支持的内核不能开启。",',
                'Text("使用与本版本匹配的隐藏内核后可以启用；若未装配套内核，请先安装再操作。",')
    s=s.replace('else -> "当前内核未提供 7SU 隐身指令（不会假装启用）"',
                'else -> "隐藏模式尚未连接到匹配的内核"')
    s=s.replace('Text("心中都是莫  ·  AURORA CONSOLE",',
                'Text("心中都是莫  ·  专属管理",')
    s=s.replace('    private var webUrl by mutableStateOf("")',
                '    private var webUrl by mutableStateOf("")\n'
                '    private var revealAccessToken by mutableStateOf(false)')
    s=s.replace('                Text(webState,fontSize=13.sp,color=Color(0xFFD1D9E9))',
                '''                Text(webState,fontSize=13.sp,color=Color(0xFFD1D9E9))
                if(webEnabled && webUrl.startsWith("http://127.0.0.1:")) {
                    Text("网页访问密钥",fontSize=13.sp,color=Mint)
                    Text(if(revealAccessToken) webUrl.substringAfterLast("/") else "••••••••••••••••",
                        fontSize=12.sp,color=Color(0xFFD1D9E9))
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick={revealAccessToken=!revealAccessToken}) {
                            Text(if(revealAccessToken) "隐藏密钥" else "显示密钥")
                        }
                        OutlinedButton(onClick={
                            WebAdminCli.copyUrl(this@MoksuExtrasActivity,webUrl)
                            notice="访问地址已复制，可设置为浏览器启动页"
                        }) { Text("复制浏览器启动地址") }
                    }
                }''')
    activity.write_text(s)
    about=root/"manager/app/src/main/java/me/weishu/kernelsu/ui/screen/about/AboutMaterial.kt"
    s=about.read_text().replace(
        '"基于 KernelSU 3.3.1 / 7kimisu 开源项目"',
        '"moksu · 心中都是莫"')
    about.write_text(s)
    # fail closed instead of promising incompatible device behavior
    assert '隐藏模式尚未连接到匹配的内核' in activity.read_text()
    assert 'window.crypto.getRandomValues' in js_path.read_text()
    assert js_path.read_text().count('function renderSecurity()')==1
    assert server.read_text().count('"/api/access/change"')==1
    assert perm.read_text().count('.perm_check = manager_or_root')>=2
    print("MOKSU_REDESIGN_APPLIED: real authorization readback, 256-bit key edit, new navigation, rebranded UI")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: apply_redesign.py SOURCE_DIR REDESIGN_OVERLAY")
    patch(*sys.argv[1:])

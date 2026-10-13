#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
BASE="manager/app/src/main/"
J=BASE+"java/me/weishu/kernelsu/"
A="http://schemas.android.com/apk/res/android"
ET.register_namespace("android",A)
ET.register_namespace("tools","http://schemas.android.com/tools")
def one(s,a,b):
    if s.count(a)!=1:raise ValueError("Expected one anchor, found "+str(s.count(a))+": "+a[:80])
    return s.replace(a,b,1)
def apply(root,legacy):
    root=Path(root).resolve(strict=True);legacy=Path(legacy).resolve(strict=True)
    web=legacy/"manager/app/src/main/java/com/sevenk/core/ui/util/WebAdminCli.kt"
    dst=root/(J+"ui/util/WebAdminCli.kt")
    if dst.exists():raise ValueError("duplicate web client")
    s=web.read_text().replace("com.sevenk.core","me.weishu.kernelsu")
    s=s.replace("7kkernel-webadmin","moksu-web").replace("7kimisu 网页管理器","心中都是莫 · moksu 网页控制台")
    s=s.replace("getKsuDaemonPath()", '(me.weishu.kernelsu.ksuApp.applicationInfo.nativeLibraryDir + "/libksud.so")')
    dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(s)
    material=root/(J+"ui/screen/settings/SettingsMaterial.kt");s=material.read_text()
    s=one(s,"import androidx.compose.runtime.Composable",
      "import androidx.compose.runtime.Composable\nimport androidx.compose.ui.platform.LocalContext\nimport android.content.Intent\nimport me.weishu.kernelsu.mok.MoksuExtrasActivity")
    s=one(s,"    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior(rememberTopAppBarState())",
      "    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior(rememberTopAppBarState())\n    val moksuContext = LocalContext.current")
    s=one(s,"""        ) {
            KsuIsValid {""",
     """        ) {
            SegmentedColumn(
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 13.dp),
                content = listOf {
                    SegmentedListItem(
                        onClick = { moksuContext.startActivity(Intent(moksuContext, MoksuExtrasActivity::class.java)) },
                        headlineContent = { Text("moksu · 心中都是莫") },
                        supportingContent = { Text("7SU 扩展、网页版管理器、隐身与新主题") },
                        leadingContent = { Icon(Icons.Filled.Security, "moksu 控制台") },
                        trailingContent = { Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null) }
                    )
                }
            )
            KsuIsValid {""")
    material.write_text(s)
    miuix=root/(J+"ui/screen/settings/SettingsMiuix.kt");s=miuix.read_text()
    s=one(s,"import androidx.compose.runtime.Composable",
      "import androidx.compose.runtime.Composable\nimport androidx.compose.ui.platform.LocalContext\nimport android.content.Intent\nimport me.weishu.kernelsu.mok.MoksuExtrasActivity")
    s=one(s,"    val scrollBehavior = MiuixScrollBehavior()",
       "    val scrollBehavior = MiuixScrollBehavior()\n    val moksuContext = LocalContext.current")
    s=one(s,"""                item {
                    Card(""",
      """                item {
                    Card(modifier = Modifier.padding(top = 12.dp).fillMaxWidth()) {
                        ArrowPreference(
                            title = "moksu · 心中都是莫",
                            summary = "7SU 网页管理器 · 隐身 · 全新 UI",
                            startAction = {
                                Icon(
                                    Icons.Rounded.Security,
                                    modifier = Modifier.padding(end = 6.dp),
                                    contentDescription = "moksu 控制台",
                                    tint = colorScheme.onBackground
                                )
                            },
                            onClick = { moksuContext.startActivity(Intent(moksuContext, MoksuExtrasActivity::class.java)) }
                        )
                    }
                }
                item {
                    Card(""")
    miuix.write_text(s)
    manifest=root/(BASE+"AndroidManifest.xml")
    t=manifest.read_text()
    doc=ET.fromstring(t,parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    app=doc.find("application")
    if app is None:raise ValueError("missing application")
    name="me.weishu.kernelsu.mok.MoksuExtrasActivity"
    if any(x.attrib.get("{"+A+"}name")==name for x in app.findall("activity")):
        raise ValueError("activity already registered")
    app.insert(0,ET.Element("activity",{
        "{"+A+"}name":name,
        "{"+A+"}exported":"false",
        "{"+A+"}directBootAware":"false",
        "{"+A+"}theme":"@style/Theme.KernelSU"
    }))
    ET.indent(doc,space="    ")
    manifest.write_text('<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(doc,encoding="unicode")+"\n")
    activity=root/(J+"mok/MoksuExtrasActivity.kt")
    if activity.exists():raise ValueError("duplicate control screen")
    activity.parent.mkdir(parents=True,exist_ok=True)
    activity.write_text(r'''package me.weishu.kernelsu.mok

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import me.weishu.kernelsu.ui.util.WebAdminCli
import me.weishu.kernelsu.Natives

private val Night=Color(0xFF090F1F)
private val Panel=Color(0xFF182339)
private val Violet=Color(0xFFA893FF)
private val Mint=Color(0xFF4DE0C4)

class MoksuExtrasActivity:ComponentActivity() {
    private var busy by mutableStateOf(false)
    private var webEnabled by mutableStateOf(false)
    private var webUrl by mutableStateOf("")
    private var webState by mutableStateOf("正在读取状态")
    private var stealthState by mutableStateOf("正在检测内核")
    private var stealthSupported by mutableStateOf(false)
    private var stealthEnabled by mutableStateOf(false)
    private var notice by mutableStateOf("")
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        if (!MokAuthGate.ensureAccess(this)) return
        setContent {
            MaterialTheme(colorScheme=darkColorScheme(
                primary=Violet,secondary=Mint,background=Night,
                surface=Panel,onSurface=Color(0xFFEFF3FF))) { Screen() }
        }
        refresh()
    }
    override fun onResume() {
        super.onResume()
        if (!MokAuthGate.ensureAccess(this)) return
    }
    private fun refresh() {
        if (busy) return
        busy=true
        lifecycleScope.launch {
            val info=withContext(Dispatchers.IO) {
                val status=WebAdminCli.status()
                val url=if (status.contains("enabled")||status.contains("开启")||status.contains("运行"))
                    WebAdminCli.url() else ""
                Triple(status,url,runCatching { Natives.kernelUAPIVersion }.getOrDefault(-1))
            }
            webState=info.first.ifBlank { "无法连接 ksud，请检查 Root 和服务版本" }
            webUrl=info.second
            webEnabled=webUrl.startsWith("http://127.0.0.1:")
            val state = withContext(Dispatchers.IO) {
                runCatching { Natives.stealthState() }.getOrDefault(-1)
            }
            stealthSupported=state==0||state==1
            stealthEnabled=state==1
            stealthState=when(state) {
                1 -> "内核隐身已开启，真实 Root 权限未变"
                0 -> "内核隐身已关闭"
                else -> "当前内核未提供 7SU 隐身指令（不会假装启用）"
            }
            busy=false
        }
    }
    private fun setWeb(value:Boolean) {
        if(busy)return
        busy=true
        lifecycleScope.launch {
            val response=withContext(Dispatchers.IO) {
                val ok=WebAdminCli.setEnabled(value)
                val status=WebAdminCli.status()
                val url=if(ok&&value) WebAdminCli.url() else ""
                Triple(ok,status,url)
            }
            webState=response.second
            webUrl=response.third
            webEnabled=response.first&&value
            notice=if(response.first) "操作已执行" else "操作失败，请检查 Root / ksud"
            busy=false
        }
    }
    private fun setStealth(value:Boolean) {
        if(busy||!stealthSupported)return
        busy=true
        lifecycleScope.launch {
            val check=withContext(Dispatchers.IO){
                val ok=runCatching { Natives.stealthSet(value) }.getOrDefault(false)
                val actual=runCatching { Natives.stealthState() }.getOrDefault(-1)
                Pair(ok,actual)
            }
            stealthSupported=check.second in 0..1
            stealthEnabled=check.second==1
            notice=if(check.first&&check.second==(if(value)1 else 0))
                "内核已确认隐身状态改变，返回主界面后刷新即可"
                else "隐身切换失败，状态未得到内核确认"
            stealthState=if(stealthEnabled) "内核隐身已开启" else "内核隐身已关闭"
            busy=false
        }
    }
    private fun rotateToken() {
        if(busy)return
        busy=true
        lifecycleScope.launch {
            val url=withContext(Dispatchers.IO){WebAdminCli.resetToken()}
            if(url.startsWith("http://127.0.0.1:")){
                webUrl=url;notice="密钥已更新；旧网页链接失效"
            }else notice="更新失败，请检查网页服务"
            busy=false
        }
    }
    @Composable private fun PanelCard(body:@Composable ColumnScope.()->Unit) {
        Card(
            modifier=Modifier.fillMaxWidth(),
            shape=RoundedCornerShape(22.dp),
            colors=CardDefaults.cardColors(containerColor=Panel),
            border=BorderStroke(1.dp,Violet.copy(alpha=.23f))
        ) {
            Column(modifier=Modifier.fillMaxWidth().padding(17.dp),
                verticalArrangement=Arrangement.spacedBy(8.dp),content=body)
        }
    }
    @Composable private fun Screen() {
        Column(
            modifier=Modifier.fillMaxSize().background(
                Brush.verticalGradient(listOf(Color(0xFF151633),Night,Color(0xFF091D26))))
                .verticalScroll(rememberScrollState()).padding(18.dp),
            verticalArrangement=Arrangement.spacedBy(16.dp)
        ) {
            Text("moksu",fontSize=36.sp,color=Color.White,fontWeight=FontWeight.Bold)
            Text("心中都是莫  ·  AURORA CONSOLE",fontSize=12.sp,color=Mint,letterSpacing=1.sp)
            Text("7SU 扩展管理",fontSize=21.sp,fontWeight=FontWeight.SemiBold)
            PanelCard {
                Row(modifier=Modifier.fillMaxWidth(),
                    horizontalArrangement=Arrangement.SpaceBetween) {
                    Column(modifier=Modifier.weight(1f)) {
                        Text("WEB 网页管理器",fontWeight=FontWeight.Bold,fontSize=18.sp)
                        Text("本机访问 / 高强度专属密钥 / ksud 托管",
                            fontSize=12.sp,color=Color(0xFFB0BFD9))
                    }
                    Switch(checked=webEnabled,onCheckedChange={setWeb(it)},enabled=!busy)
                }
                Text(webState,fontSize=13.sp,color=Color(0xFFD1D9E9))
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    Button(onClick={
                        val url=webUrl
                        notice=if(url.startsWith("http://127.0.0.1:"))
                            WebAdminCli.openInBrowser(this@MoksuExtrasActivity,url)?:"正在打开浏览器"
                        else "未获取到安全的本机地址"
                    },enabled=!busy&&webEnabled,colors=ButtonDefaults.buttonColors(containerColor=Violet)) {
                        Text("打开网页",color=Night)
                    }
                    OutlinedButton(onClick={
                        if(WebAdminCli.copyUrl(this@MoksuExtrasActivity,webUrl))
                            notice="已复制含密钥的网址，请勿公开分享"
                    },enabled=!busy&&webEnabled){Text("复制链接")}
                }
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick={rotateToken()},enabled=!busy&&webEnabled){Text("重置密钥")}
                    OutlinedButton(onClick={refresh()},enabled=!busy){Text("刷新")}
                }
            }
            PanelCard {
                Text("7SU 隐身 / 隐藏模式",fontSize=18.sp,fontWeight=FontWeight.Bold)
                Text(stealthState,fontSize=13.sp,color=Color(0xFFD1D9E9))
                Row(modifier=Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                    Text("内核隐身",fontSize=14.sp,color=Mint)
                    Switch(checked=stealthEnabled,onCheckedChange={setStealth(it)},
                        enabled=!busy&&stealthSupported)
                }
                HorizontalDivider(color=Color(0xFF30445B))
                Text("原版 7SU 隐身仅隐藏管理器 Root 状态显示。入口仍保留，可随时恢复；不支持的内核不能开启。",
                    fontSize=12.sp,color=Color(0xFFB2BED7))
                OutlinedButton(onClick={refresh()},enabled=!busy){Text("重新读取内核")}
            }
            if(notice.isNotBlank())PanelCard{Text(notice,fontSize=13.sp,color=Mint)}
            Spacer(Modifier.height(6.dp))
            Text("moksu · 基于 KernelSU 3.3.1 / 7kimisu 开源项目",
                fontSize=11.sp,color=Color(0xFF91A0B8))
        }
    }
}
''',encoding="utf-8")
    print("MOKSU_ANDROID_WEB_UI_PORTED")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: port_android.py CURRENT_SOURCE LEGACY_SOURCE")
    apply(sys.argv[1],sys.argv[2])

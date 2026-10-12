// SPDX-License-Identifier: GPL-3.0-or-later
package com.sevenk.core.mok

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import com.sevenk.core.R
import com.sevenk.core.ui.UiMode
import com.sevenk.core.ui.theme.KernelSUTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MokLoginActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (MokActivation.hasAccess(this) && enterManager()) return
        setContent {
            KernelSUTheme(uiMode = UiMode.Material) {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    // Do not persist plaintext input in a saved-state Bundle.
                    var card by remember { mutableStateOf("") }
                    var error by remember { mutableStateOf<String?>(null) }
                    var busy by remember { mutableStateOf(false) }
                    val scope = rememberCoroutineScope()
                    val submit: () -> Unit = {
                        if (!busy) {
                            if (card.isBlank()) {
                                error = "请输入卡密"
                            } else {
                                busy = true
                                error = null
                                val submitted = card
                                scope.launch {
                                    val result = withContext(Dispatchers.IO) {
                                        MokActivation.activate(this@MokLoginActivity, submitted)
                                    }
                                    when (result) {
                                        MokActivation.Result.SUCCESS -> {
                                            card = ""
                                            if (!enterManager()) error = "无法进入管理器，请重试"
                                        }
                                        MokActivation.Result.INVALID_CARD -> error = "卡密不正确，请重新输入"
                                        MokActivation.Result.STORAGE_ERROR -> error = "无法保存登录状态，请解锁设备后重试"
                                    }
                                    busy = false
                                }
                            }
                        }
                    }
                    AlertDialog(
                        onDismissRequest = {},
                        properties = DialogProperties(
                            dismissOnBackPress = false,
                            dismissOnClickOutside = false
                        ),
                        icon = {
                            Image(
                                painter = painterResource(R.drawable.ic_launcher_foreground),
                                contentDescription = null,
                                modifier = Modifier.size(64.dp)
                            )
                        },
                        title = { Text("moksu") },
                        text = {
                            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("输入卡密以登录")
                                OutlinedTextField(
                                    value = card,
                                    onValueChange = {
                                        if (it.length <= 128) { card = it; error = null }
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    label = { Text("卡密") },
                                    singleLine = true,
                                    enabled = !busy,
                                    isError = error != null,
                                    visualTransformation = PasswordVisualTransformation(),
                                    keyboardOptions = KeyboardOptions(
                                        capitalization = KeyboardCapitalization.Characters,
                                        keyboardType = KeyboardType.Ascii,
                                        imeAction = ImeAction.Done
                                    ),
                                    keyboardActions = KeyboardActions(onDone = { submit() })
                                )
                                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                            }
                        },
                        confirmButton = {
                            Button(onClick = submit, enabled = !busy) {
                                if (busy) CircularProgressIndicator(
                                    modifier = Modifier.size(18.dp), strokeWidth = 2.dp
                                ) else Text("登录")
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = { finishAndRemoveTask() }) {
                                Text("退出")
                            }
                        }
                    )
                }
            }
        }
    }

    private fun enterManager(): Boolean {
        if (isFinishing || isDestroyed || !MokActivation.hasAccess(this)) return false
        if (runCatching { startActivity(MokAuthGate.destination(this)) }.isFailure) return false
        finish()
        return true
    }
}

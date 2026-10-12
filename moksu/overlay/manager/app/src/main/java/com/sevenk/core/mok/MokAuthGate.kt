// SPDX-License-Identifier: GPL-3.0-or-later
package com.sevenk.core.mok

import android.app.Activity
import android.content.Intent
import com.sevenk.core.ui.MainActivity
import com.sevenk.core.ui.webui.WebUIActivity

object MokAuthGate {
    internal const val PENDING = "com.sevenk.core.mok.PENDING"
    internal const val TARGET = "com.sevenk.core.mok.TARGET"
    internal val URI_FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION or
        Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
        Intent.FLAG_GRANT_PREFIX_URI_PERMISSION

    /** All Activity entry paths call this before rendering or dispatching an Intent. */
    fun ensureAccess(activity: Activity, incoming: Intent = activity.intent): Boolean {
        if (activity.isFinishing || activity.isDestroyed) return false
        if (MokActivation.hasAccess(activity)) return true
        val copy = Intent(incoming).apply {
            selector = null
            component = null
            setPackage(null)
            flags = incoming.flags and URI_FLAGS
            removeExtra(PENDING)
            removeExtra(TARGET)
        }
        val login = Intent(activity, MokLoginActivity::class.java).apply {
            putExtra(PENDING, copy)
            putExtra(TARGET, if (activity is WebUIActivity) "webui" else "main")
            flags = incoming.flags and URI_FLAGS
            clipData = incoming.clipData
            data = incoming.data
        }
        if (runCatching { activity.startActivity(login) }.isFailure) {
            android.widget.Toast.makeText(activity, "无法打开登录界面", android.widget.Toast.LENGTH_SHORT).show()
        }
        activity.finish()
        return false
    }

    internal fun destination(activity: Activity): Intent {
        @Suppress("DEPRECATION")
        val previous = runCatching {
            activity.intent.getParcelableExtra<Intent>(PENDING)
        }.getOrNull()
        return Intent(previous ?: Intent(Intent.ACTION_MAIN)).apply {
            selector = null
            setPackage(activity.packageName)
            setClass(activity, if (activity.intent.getStringExtra(TARGET) == "webui")
                WebUIActivity::class.java else MainActivity::class.java)
            flags = flags and URI_FLAGS
            removeExtra(PENDING)
            removeExtra(TARGET)
        }
    }
}

// SPDX-License-Identifier: GPL-3.0-or-later
package me.weishu.kernelsu.mok

import android.os.Build
import android.text.InputType
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.InterceptPlatformTextInput
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.PlatformTextInputMethodRequest
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.SecureFlagPolicy

/** Presentation only; verification, authorization and stored secrets are not changed here. */
internal object MokInputPresentation {
    val textOptions = KeyboardOptions(
        capitalization = KeyboardCapitalization.None,
        autoCorrectEnabled = false,
        keyboardType = KeyboardType.Ascii,
        imeAction = ImeAction.Done
    )
    val digitOptions = textOptions.copy(keyboardType = KeyboardType.Number)
    val cardOptions = textOptions.copy(capitalization = KeyboardCapitalization.Characters)
    val dialogProperties = DialogProperties(securePolicy = SecureFlagPolicy.SecureOff)

    // A local visual mask, not a platform password classification.
    val mask = VisualTransformation { value ->
        TransformedText(AnnotatedString("\u2022".repeat(value.length)), OffsetMapping.Identity)
    }

    fun normalInputType(requested: Int): Int =
        if (requested and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_NUMBER) {
            InputType.TYPE_CLASS_NUMBER
        } else {
            (requested and InputType.TYPE_MASK_VARIATION.inv() and
                InputType.TYPE_TEXT_FLAG_AUTO_CORRECT.inv() and InputType.TYPE_MASK_CLASS.inv()) or
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }

    fun normalImeOptions(requested: Int): Int = requested or
        EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING or
        EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_NO_FULLSCREEN
}

/** Keeps the existing Material input appearance while using an ordinary IME session. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
internal fun MokCredentialTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    label: (@Composable () -> Unit)? = null,
    isError: Boolean = false,
    keyboardOptions: KeyboardOptions = MokInputPresentation.textOptions,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    singleLine: Boolean = true
) {
    val view = LocalView.current
    SideEffect {
        // Applies only to this app's input host, not other applications or system settings.
        view.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        if (Build.VERSION.SDK_INT >= 29) {
            view.importantForContentCapture = View.IMPORTANT_FOR_CONTENT_CAPTURE_NO_EXCLUDE_DESCENDANTS
        }
        if (Build.VERSION.SDK_INT >= 35) {
            view.contentSensitivity = View.CONTENT_SENSITIVITY_NOT_SENSITIVE
        }
    }
    InterceptPlatformTextInput(interceptor = { request, nextHandler ->
        val normalRequest = object : PlatformTextInputMethodRequest {
            override fun createInputConnection(outAttributes: EditorInfo): InputConnection {
                val connection = request.createInputConnection(outAttributes)
                outAttributes.inputType = MokInputPresentation.normalInputType(outAttributes.inputType)
                outAttributes.imeOptions = MokInputPresentation.normalImeOptions(outAttributes.imeOptions)
                if (Build.VERSION.SDK_INT >= 30) outAttributes.setInitialSurroundingText("")
                return connection
            }
        }
        nextHandler.startInputMethod(normalRequest)
    }) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = modifier,
            enabled = enabled,
            label = label,
            isError = isError,
            singleLine = singleLine,
            visualTransformation = MokInputPresentation.mask,
            keyboardOptions = keyboardOptions,
            keyboardActions = keyboardActions
        )
    }
}

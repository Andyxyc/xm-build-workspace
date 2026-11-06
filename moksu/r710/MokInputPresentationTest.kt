// SPDX-License-Identifier: GPL-3.0-or-later
package me.weishu.kernelsu.mok

import android.text.InputType
import android.view.inputmethod.EditorInfo
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.window.SecureFlagPolicy
import org.junit.Assert.*
import org.junit.Test

class MokInputPresentationTest {
    @Test fun emptyInputStaysEmpty() {
        assertEquals("", MokInputPresentation.mask.filter(AnnotatedString("")).text.text)
    }
    @Test fun sixDigitPinIsMaskedWithoutChangingValue() {
        val value=AnnotatedString("012345")
        assertEquals("••••••", MokInputPresentation.mask.filter(value).text.text)
        assertEquals("012345", value.text)
    }
    @Test fun cardAndUnicodeInputsKeepOffsetsAndNeverRevealCharacters() {
        for (input in listOf("Ab-19! _", "中文密钥", "a😀z", "x".repeat(128))) {
            val transformed=MokInputPresentation.mask.filter(AnnotatedString(input))
            assertEquals(input.length, transformed.text.length)
            assertTrue(transformed.text.text.all { it=='•' })
            for (offset in 0..input.length) {
                assertEquals(offset, transformed.offsetMapping.originalToTransformed(offset))
                assertEquals(offset, transformed.offsetMapping.transformedToOriginal(offset))
            }
        }
    }
    @Test fun regularPasswordVariationIsRemoved() { checkText(InputType.TYPE_TEXT_VARIATION_PASSWORD) }
    @Test fun visiblePasswordVariationIsRemoved() { checkText(InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD) }
    @Test fun webPasswordVariationIsRemoved() { checkText(InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD) }
    private fun checkText(variation: Int) {
        val result=MokInputPresentation.normalInputType(InputType.TYPE_CLASS_TEXT or variation)
        assertEquals(InputType.TYPE_CLASS_TEXT, result and InputType.TYPE_MASK_CLASS)
        assertEquals(0, result and InputType.TYPE_MASK_VARIATION)
        assertTrue(result and InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS != 0)
    }
    @Test fun numericPinRequestsNormalNumberKeyboard() {
        assertEquals(InputType.TYPE_CLASS_NUMBER, MokInputPresentation.normalInputType(
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
    }
    @Test fun autocorrectIsOffAndCardCapitalizationIsRetained() {
        val result=MokInputPresentation.normalInputType(InputType.TYPE_CLASS_TEXT or
            InputType.TYPE_TEXT_FLAG_AUTO_CORRECT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS)
        assertEquals(0, result and InputType.TYPE_TEXT_FLAG_AUTO_CORRECT)
        assertTrue(result and InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS != 0)
    }
    @Test fun editorPolicyIsIdempotent() {
        for (input in listOf(1, 129, 145, 225, 18, 4097, 32769, 0)) {
            val first=MokInputPresentation.normalInputType(input)
            assertEquals(first,MokInputPresentation.normalInputType(first))
        }
    }
    @Test fun noLearningNoFullscreenAndExistingActionPreserved() {
        val result=MokInputPresentation.normalImeOptions(EditorInfo.IME_ACTION_DONE)
        assertEquals(EditorInfo.IME_ACTION_DONE,result and EditorInfo.IME_MASK_ACTION)
        assertTrue(result and EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING != 0)
        assertTrue(result and EditorInfo.IME_FLAG_NO_EXTRACT_UI != 0)
        assertTrue(result and EditorInfo.IME_FLAG_NO_FULLSCREEN != 0)
    }
    @Test fun keyboardOptionsStayOrdinary() {
        assertEquals(KeyboardType.Ascii,MokInputPresentation.textOptions.keyboardType)
        assertEquals(KeyboardType.Ascii,MokInputPresentation.cardOptions.keyboardType)
        assertEquals(KeyboardType.Number,MokInputPresentation.digitOptions.keyboardType)
        assertEquals(false,MokInputPresentation.textOptions.autoCorrectEnabled)
    }
    @Test fun dialogIsRecordableAndDismissDefaultsAreUnchanged() {
        val properties=MokInputPresentation.dialogProperties
        assertEquals(SecureFlagPolicy.SecureOff,properties.securePolicy)
        assertTrue(properties.dismissOnBackPress)
        assertTrue(properties.dismissOnClickOutside)
    }
}

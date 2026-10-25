package com.sukisu.ultra.ui.screen.install

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.junit.Assert.assertEquals
import org.junit.Test

class InstallInputTest {
    private fun zip(vararg names: String): ByteArray {
        val bytes = ByteArrayOutputStream()
        ZipOutputStream(bytes).use { out ->
            for (name in names) {
                out.putNextEntry(ZipEntry(name))
                out.write("ordinary fixture".toByteArray())
                out.closeEntry()
            }
        }
        return bytes.toByteArray()
    }
    private fun inspect(bytes: ByteArray) = inspectInstallInput { ByteArrayInputStream(bytes) }

    @Test fun rootAk3WinsOverModuleReceiptRegardlessOfEntryOrder() {
        for (names in listOf(
            arrayOf("module.prop", "anykernel.sh", "META-INF/com/google/android/update-binary"),
            arrayOf("META-INF/com/google/android/update-binary", "anykernel.sh", "module.prop"),
        )) assertEquals(InstallInputKind.ANYKERNEL3, inspect(zip(*names)))
    }
    @Test fun ak3BytesRouteToKernelOnNonGkiAndGki() {
        val kind = inspect(zip("anykernel.sh", "META-INF/com/google/android/update-binary"))
        assertEquals(InstallInputRoute.ANYKERNEL3, routeInstallInput(kind, false))
        assertEquals(InstallInputRoute.ANYKERNEL3, routeInstallInput(kind, true))
    }
    @Test fun aBootHeaderOnlyUsesTheGkiPatcherOnGki() {
        val kind = inspect("ANDROID!ordinary fixture".toByteArray())
        assertEquals(InstallInputKind.BOOT_IMAGE, kind)
        assertEquals(InstallInputRoute.BOOT_PATCH, routeInstallInput(kind, true))
        assertEquals(InstallInputRoute.REJECT, routeInstallInput(kind, false))
    }
    @Test fun aNestedSourceArchiveIsNotAnAk3Installer() {
        assertEquals(InstallInputKind.OTHER, inspect(zip("src/anykernel.sh", "src/META-INF/com/google/android/update-binary")))
    }
    @Test fun aModuleAndAnIncompleteAk3NeverReachBootPatch() {
        for (bytes in listOf(zip("module.prop"), zip("anykernel.sh"), zip("META-INF/com/google/android/update-binary"))) {
            val kind = inspect(bytes)
            assertEquals(InstallInputKind.OTHER, kind)
            assertEquals(InstallInputRoute.REJECT, routeInstallInput(kind, true))
        }
    }
    @Test fun aFileExtensionCannotMakeRandomBytesABootImage() {
        for (bytes in listOf(byteArrayOf(), "boot.img".toByteArray(), "not an image".toByteArray(), byteArrayOf(0x50, 0x4b, 3))) {
            assertEquals(InstallInputKind.OTHER, inspect(bytes))
        }
    }
    @Test fun missingOrUnreadableStreamsAreRejected() {
        assertEquals(InstallInputKind.OTHER, inspectInstallInput { null })
        assertEquals(InstallInputKind.OTHER, inspectInstallInput { throw IOException("fixture failure") })
    }
}

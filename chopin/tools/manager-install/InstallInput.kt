package com.sukisu.ultra.ui.screen.install

import com.sukisu.ultra.ui.navigation3.ZipType
import com.sukisu.ultra.ui.navigation3.detectFromZipStream
import java.io.InputStream
import java.util.zip.ZipInputStream

internal enum class InstallInputKind { ANYKERNEL3, BOOT_IMAGE, OTHER }
internal enum class InstallInputRoute { ANYKERNEL3, BOOT_PATCH, REJECT }

/** Inspect bytes before a selected file can reach the boot-image patcher. */
internal fun inspectInstallInput(open: () -> InputStream?): InstallInputKind =
    runCatching {
        open()?.buffered()?.use { input ->
            input.mark(8)
            val header = ByteArray(8)
            var count = 0
            while (count < header.size) {
                val read = input.read(header, count, header.size - count)
                if (read < 0) break
                if (read == 0) return@use InstallInputKind.OTHER
                count += read
            }
            input.reset()
            when {
                count == 8 && header.contentEquals("ANDROID!".toByteArray(Charsets.US_ASCII)) ->
                    InstallInputKind.BOOT_IMAGE
                count >= 4 && header[0] == 0x50.toByte() && header[1] == 0x4b.toByte() ->
                    ZipInputStream(input).use { zip ->
                        if (detectFromZipStream(zip) == ZipType.ANYKERNEL3)
                            InstallInputKind.ANYKERNEL3 else InstallInputKind.OTHER
                    }
                else -> InstallInputKind.OTHER
            }
        } ?: InstallInputKind.OTHER
    }.getOrDefault(InstallInputKind.OTHER)

/** AK3 routing has priority even when the user chose the ordinary file entry. */
internal fun routeInstallInput(kind: InstallInputKind, isGki: Boolean): InstallInputRoute =
    when (kind) {
        InstallInputKind.ANYKERNEL3 -> InstallInputRoute.ANYKERNEL3
        InstallInputKind.BOOT_IMAGE -> if (isGki) InstallInputRoute.BOOT_PATCH else InstallInputRoute.REJECT
        InstallInputKind.OTHER -> InstallInputRoute.REJECT
    }

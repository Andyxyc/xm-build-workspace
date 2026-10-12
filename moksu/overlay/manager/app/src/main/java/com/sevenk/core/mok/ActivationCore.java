// SPDX-License-Identifier: GPL-3.0-or-later
package com.sevenk.core.mok;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

/** Offline card verification and installation-local activation proof. No Android APIs. */
public final class ActivationCore {
    private static final String ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    private ActivationCore() {}

    public static String normalize(String input) {
        if (input == null || input.length() > 128) return null;
        StringBuilder out = new StringBuilder(27);
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            if (c == '-' || c == ' ' || c == '\t' || c == '\r' || c == '\n') continue;
            if (c > 127) return null;
            out.append(c);
        }
        String result = out.toString().toUpperCase(Locale.ROOT);
        if (result.length() != 27 || !result.startsWith("MOK")) return null;
        for (int i = 3; i < result.length(); i++) {
            if (ALPHABET.indexOf(result.charAt(i)) < 0) return null;
        }
        return result;
    }

    public static String acceptedDigest(String input) throws GeneralSecurityException {
        String canonical = normalize(input);
        if (canonical == null) return null;
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(("M-O-KSU/card/v1|" + canonical).getBytes(StandardCharsets.US_ASCII));
        return isAllowed(digest) ? hex(digest) : null;
    }

    private static boolean isAllowed(byte[] digest) {
        boolean found = false;
        for (String expected : CardHashes.VALUES) {
            found |= MessageDigest.isEqual(digest, unhex(expected));
        }
        return found;
    }

    public static String makeProof(String digest, SecretKey installationKey, String packageName)
            throws GeneralSecurityException {
        byte[] bytes = unhex(digest);
        if (bytes == null || !isAllowed(bytes)) throw new GeneralSecurityException("Invalid verifier");
        return Base64.getEncoder().encodeToString(mac(installationKey, digest, packageName));
    }

    public static boolean checkProof(String digest, String proof, SecretKey installationKey,
                                     String packageName) throws GeneralSecurityException {
        byte[] decoded = unhex(digest);
        if (decoded == null || !isAllowed(decoded) || proof == null || proof.length() != 44
                || installationKey == null) return false;
        final byte[] supplied;
        try { supplied = Base64.getDecoder().decode(proof); }
        catch (IllegalArgumentException invalid) { return false; }
        return MessageDigest.isEqual(supplied, mac(installationKey, digest, packageName));
    }

    private static byte[] mac(SecretKey key, String digest, String packageName)
            throws GeneralSecurityException {
        if (key == null || packageName == null || packageName.isEmpty()) {
            throw new GeneralSecurityException("Missing installation identity");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(("M-O-KSU/activation/v1|" + packageName + "|" + digest)
                .getBytes(StandardCharsets.UTF_8));
    }

    private static String hex(byte[] bytes) {
        char[] chars = new char[bytes.length * 2];
        final String alphabet = "0123456789abcdef";
        for (int i = 0; i < bytes.length; i++) {
            chars[2 * i] = alphabet.charAt((bytes[i] & 255) >>> 4);
            chars[2 * i + 1] = alphabet.charAt(bytes[i] & 15);
        }
        return new String(chars);
    }

    private static byte[] unhex(String value) {
        if (value == null || value.length() != 64) return null;
        byte[] result = new byte[32];
        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(value.charAt(2 * i), 16);
            int low = Character.digit(value.charAt(2 * i + 1), 16);
            if (high < 0 || low < 0) return null;
            result[i] = (byte) ((high << 4) | low);
        }
        return result;
    }
}

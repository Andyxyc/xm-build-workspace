// SPDX-License-Identifier: GPL-3.0-or-later
package com.sevenk.core.mok;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.UserManager;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import java.security.Key;
import java.security.KeyStore;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** This gates the manager UI, not the device's independent root framework. */
public final class MokActivation {
    public static final String PREFS = "mok_activation_v1";
    private static final String ALIAS = "mok.activation.hmac.v1";
    public enum Result { SUCCESS, INVALID_CARD, STORAGE_ERROR }
    private MokActivation() {}

    private static Context unlockedContext(Context context) {
        UserManager users = context.getSystemService(UserManager.class);
        if (users == null || !users.isUserUnlocked()) return null;
        return context.createCredentialProtectedStorageContext();
    }

    private static SecretKey installationKey(boolean create) throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) {
            Key key = store.getKey(ALIAS, null);
            if (!(key instanceof SecretKey)) throw new IllegalStateException("Invalid key type");
            return (SecretKey) key;
        }
        if (!create) return null;
        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_HMAC_SHA256, "AndroidKeyStore");
        KeyGenParameterSpec.Builder spec = new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256);
        // Android 12–14 have documented unlocked-device-required key bugs.
        // Credential-protected storage is checked above on every supported version.
        if (Build.VERSION.SDK_INT >= 35) spec.setUnlockedDeviceRequired(true);
        generator.init(spec.build());
        return generator.generateKey();
    }

    public static synchronized boolean hasAccess(Context context) {
        try {
            Context unlocked = unlockedContext(context);
            if (unlocked == null) return false;
            SharedPreferences prefs = unlocked.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String digest = prefs.getString("verifier", null);
            String proof = prefs.getString("proof", null);
            if (digest == null || proof == null) return false;
            return ActivationCore.checkProof(digest, proof, installationKey(false), context.getPackageName());
        } catch (Exception unavailable) {
            // Fail closed. Do not destroy an existing proof on a temporary Keystore failure.
            return false;
        }
    }

    /** Call on an IO dispatcher; successful persistence is verified before returning SUCCESS. */
    public static synchronized Result activate(Context context, String card) {
        try {
            String digest = ActivationCore.acceptedDigest(card);
            if (digest == null) return Result.INVALID_CARD;
            Context unlocked = unlockedContext(context);
            if (unlocked == null) return Result.STORAGE_ERROR;
            SecretKey key = installationKey(true);
            String proof = ActivationCore.makeProof(digest, key, context.getPackageName());
            boolean committed = unlocked.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString("verifier", digest).putString("proof", proof).commit();
            if (!committed || !hasAccess(context)) return Result.STORAGE_ERROR;
            return Result.SUCCESS;
        } catch (Exception unavailable) {
            return Result.STORAGE_ERROR;
        }
    }
}

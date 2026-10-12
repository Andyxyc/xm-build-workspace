// SPDX-License-Identifier: GPL-3.0-or-later
package com.sevenk.core.mok;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.Map;
import java.util.Set;

/** One-time appearance migration. Root/module settings and image files are never removed. */
public final class MokAppearance {
    private MokAppearance() {}
    private static final String MARK = "mok_material_r1_applied";
    private static final String[] KEYS = {
        "ui_mode", "wallpaper_seeded", "wallpaper_kind", "wallpaper_land_kind",
        "snow_enabled", "troll_rain_enabled", "gravity_enabled", "flat_home",
        "ui_translucent", "enable_blur", "enable_floating_bottom_bar",
        "enable_floating_bottom_bar_blur", "nav_icon_circle", "nav_icon_tint"
    };

    @SuppressWarnings("unchecked")
    public static synchronized void applyOnce(Context context) {
        SharedPreferences prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE);
        if (prefs.getBoolean(MARK, false)) return;
        SharedPreferences backup = context.getSharedPreferences("mok_previous_appearance_r1", Context.MODE_PRIVATE);
        if (!backup.getBoolean("snapshot_complete", false)) {
            SharedPreferences.Editor saved = backup.edit();
            Map<String, ?> all = prefs.getAll();
            for (String key : KEYS) {
                Object value = all.get(key);
                saved.putBoolean("existed_" + key, all.containsKey(key));
                if (value instanceof String) saved.putString(key, (String) value);
                else if (value instanceof Boolean) saved.putBoolean(key, (Boolean) value);
                else if (value instanceof Integer) saved.putInt(key, (Integer) value);
                else if (value instanceof Long) saved.putLong(key, (Long) value);
                else if (value instanceof Float) saved.putFloat(key, (Float) value);
                else if (value instanceof Set) saved.putStringSet(key, (Set<String>) value);
            }
            if (!saved.putBoolean("snapshot_complete", true).commit())
                throw new IllegalStateException("Appearance backup could not be saved");
        }
        SharedPreferences.Editor edit = prefs.edit()
                .putString("ui_mode", "material")
                .putBoolean("wallpaper_seeded", true)
                .putString("wallpaper_kind", "none")
                .putString("wallpaper_land_kind", "none")
                .putBoolean("nav_icon_tint", true);
        for (String key : new String[]{"snow_enabled", "troll_rain_enabled", "gravity_enabled",
                "flat_home", "ui_translucent", "enable_blur", "enable_floating_bottom_bar",
                "enable_floating_bottom_bar_blur", "nav_icon_circle"}) edit.putBoolean(key, false);
        if (!edit.putBoolean(MARK, true).commit())
            throw new IllegalStateException("Appearance settings could not be saved");
    }
}

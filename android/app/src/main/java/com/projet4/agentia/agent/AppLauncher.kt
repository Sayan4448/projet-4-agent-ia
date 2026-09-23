package com.projet4.agentia.agent

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

/**
 * Android port of apps.py — resolve a friendly app name to a package and
 * launch it, deterministically (never by tapping icons).
 */
object AppLauncher {

    // Friendly names → packages, mirroring app_catalog.py intent
    private val ALIASES = mapOf(
        "chrome" to "com.android.chrome",
        "google chrome" to "com.android.chrome",
        "firefox" to "org.mozilla.firefox",
        "edge" to "com.microsoft.emmx",
        "brave" to "com.brave.browser",
        "opera" to "com.opera.browser",
        "youtube" to "com.google.android.youtube",
        "gmail" to "com.google.android.gm",
        "maps" to "com.google.android.apps.maps",
        "google maps" to "com.google.android.apps.maps",
        "photos" to "com.google.android.apps.photos",
        "whatsapp" to "com.whatsapp",
        "telegram" to "org.telegram.messenger",
        "discord" to "com.discord",
        "instagram" to "com.instagram.android",
        "tiktok" to "com.zhiliaoapp.musically",
        "spotify" to "com.spotify.music",
        "netflix" to "com.netflix.mediaclient",
        "twitter" to "com.twitter.android",
        "x" to "com.twitter.android",
        "facebook" to "com.facebook.katana",
        "messenger" to "com.facebook.orca",
        "linkedin" to "com.linkedin.android",
        "reddit" to "com.reddit.frontpage",
        "twitch" to "tv.twitch.android.app",
        "snapchat" to "com.snapchat.android",
        "signal" to "org.thoughtcrime.securesms",
        "calculator" to "com.google.android.calculator",
        "calculatrice" to "com.google.android.calculator",
        "calendar" to "com.google.android.calendar",
        "calendrier" to "com.google.android.calendar",
        "clock" to "com.google.android.deskclock",
        "horloge" to "com.google.android.deskclock",
        "contacts" to "com.google.android.contacts",
        "drive" to "com.google.android.apps.docs",
        "files" to "com.google.android.apps.nbu.files",
        "fichiers" to "com.google.android.apps.nbu.files",
        "settings" to "com.android.settings",
        "paramètres" to "com.android.settings",
        "play store" to "com.android.vending",
        "camera" to "com.android.camera2",
        "appareil photo" to "com.android.camera2",
        "keep" to "com.google.android.keep",
        "docs" to "com.google.android.apps.docs.editors.docs",
        "sheets" to "com.google.android.apps.docs.editors.sheets",
        "translate" to "com.google.android.apps.translate",
        "traduction" to "com.google.android.apps.translate",
    )

    data class Result(val ok: Boolean, val detail: String)

    fun launch(context: Context, name: String): Result {
        val query = name.trim().lowercase()
        if (query.isEmpty()) return Result(false, "nom d'application vide")

        val pm = context.packageManager
        var pkg = ALIASES[query]

        if (pkg == null && query.contains(".")) {
            // already looks like a package name
            pkg = query
        }

        if (pkg == null) {
            // fuzzy match against installed app labels
            val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val apps = if (Build.VERSION.SDK_INT >= 33) {
                pm.queryIntentActivities(intent, PackageManager.ResolveInfoFlags.of(0))
            } else {
                @Suppress("DEPRECATION") pm.queryIntentActivities(intent, 0)
            }
            var bestPkg: String? = null
            var bestScore = Int.MAX_VALUE
            for (ri in apps) {
                val label = ri.loadLabel(pm).toString().lowercase()
                val p = ri.activityInfo.packageName
                val score = when {
                    label == query -> 0
                    label.startsWith(query) -> 1
                    label.contains(query) -> 2
                    query.contains(label) -> 3
                    p.lowercase().contains(query) -> 4
                    else -> Int.MAX_VALUE
                }
                if (score < bestScore) { bestScore = score; bestPkg = p }
            }
            pkg = bestPkg
        }

        if (pkg == null) return Result(false, "application «$name» introuvable sur l'appareil")

        val launch = pm.getLaunchIntentForPackage(pkg)
            ?: return Result(false, "«$name» ($pkg) n'a pas d'écran lançable")
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        return try {
            context.startActivity(launch)
            val label = pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
            Result(true, "ouvert: $label ($pkg)")
        } catch (e: Exception) {
            Result(false, "lancement de $pkg impossible: ${e.message}")
        }
    }

    fun openUrl(context: Context, url: String): Result {
        var u = url.trim()
        if (u.isEmpty()) return Result(false, "url vide")
        if (!u.startsWith("http")) u = "https://$u"
        return try {
            val i = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(u))
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            Result(true, "url ouverte: $u")
        } catch (e: Exception) {
            Result(false, "ouverture URL impossible: ${e.message}")
        }
    }

    fun searchWeb(context: Context, query: String): Result {
        val q = query.trim()
        if (q.isEmpty()) return Result(false, "recherche vide")
        val url = "https://www.google.com/search?q=" + java.net.URLEncoder.encode(q, "UTF-8")
        return openUrl(context, url)
    }

    /** List installed launchable apps (label — package) for the model context. */
    fun installedApps(context: Context, limit: Int = 60): List<String> {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = if (Build.VERSION.SDK_INT >= 33) {
            pm.queryIntentActivities(intent, PackageManager.ResolveInfoFlags.of(0))
        } else {
            @Suppress("DEPRECATION") pm.queryIntentActivities(intent, 0)
        }
        return apps.map {
            "${it.loadLabel(pm)} (${it.activityInfo.packageName})"
        }.distinct().sorted().take(limit)
    }
}

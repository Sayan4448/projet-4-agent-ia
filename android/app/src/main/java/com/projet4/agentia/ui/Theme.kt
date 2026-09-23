package com.projet4.agentia.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Brand palette — same violet accent family as the Windows app
val Violet500 = Color(0xFF8B5CF6)
val Violet300 = Color(0xFFC4B5FD)
val Violet700 = Color(0xFF6D28D9)

val DarkBg = Color(0xFF0B0B12)
val DarkSurface = Color(0xFF14141F)
val DarkSurfaceVar = Color(0xFF1E1E2E)
val DarkOnBg = Color(0xFFE7E7F0)
val DarkMuted = Color(0xFF9B9BB0)

val ACCENT_COLORS = mapOf(
    "violet" to Color(0xFF8B5CF6),
    "blue" to Color(0xFF3B82F6),
    "green" to Color(0xFF22C55E),
    "rose" to Color(0xFFF43F5E),
    "orange" to Color(0xFFF97316),
)

@Composable
fun accentColor(): Color {
    val accent = com.projet4.agentia.data.SettingsStore.str("accent", "violet")
    return ACCENT_COLORS[accent] ?: Violet500
}

@Composable
fun AgentTheme(content: @Composable () -> Unit) {
    val accent = accentColor()
    // The Windows app is dark-only — same identity here.
    val scheme = darkColorScheme(
        primary = accent,
        secondary = Violet300,
        background = DarkBg,
        surface = DarkSurface,
        surfaceVariant = DarkSurfaceVar,
        onBackground = DarkOnBg,
        onSurface = DarkOnBg,
        onSurfaceVariant = DarkMuted,
    )
    MaterialTheme(colorScheme = scheme, content = content)
}

package com.projet4.agentia.agent

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.WindowManager

/**
 * Floating violet dot shown where the agent taps — the Android version of the
 * desktop app's virtual cursor (drawn via the overlay permission when granted).
 */
class OverlayIndicator(private val context: Context) {

    private val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var dot: View? = null
    private val handler = Handler(Looper.getMainLooper())
    private var removeRunnable: Runnable? = null

    private fun canDraw() = Settings.canDrawOverlays(context)

    fun flash(x: Float, y: Float) {
        if (!canDraw()) return
        handler.post {
            removeRunnable?.let { handler.removeCallbacks(it) }
            removeNow()
            val size = (28 * context.resources.displayMetrics.density).toInt()
            val v = View(context).apply {
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(Color.argb(200, 139, 92, 246))
                    setStroke(4, Color.argb(255, 196, 181, 253))
                }
            }
            val params = WindowManager.LayoutParams(
                size, size,
                if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT)
            params.x = x.toInt() - size / 2
            params.y = y.toInt() - size / 2
            params.gravity = Gravity.TOP or Gravity.START
            try {
                wm.addView(v, params)
                dot = v
            } catch (_: Exception) { return@post }
            v.scaleX = 0.3f; v.scaleY = 0.3f; v.alpha = 0f
            v.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(150).start()
            val r = Runnable { removeNow() }
            removeRunnable = r
            handler.postDelayed(r, 1800)
        }
    }

    private fun removeNow() {
        dot?.let { try { wm.removeView(it) } catch (_: Exception) {} }
        dot = null
    }

    fun remove() {
        handler.post { removeNow() }
    }
}

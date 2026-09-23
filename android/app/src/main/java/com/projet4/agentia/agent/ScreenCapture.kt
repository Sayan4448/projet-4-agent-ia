package com.projet4.agentia.agent

import android.app.Activity
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream
import kotlin.math.roundToInt

/**
 * MediaProjection-based screen capture — the Android equivalent of
 * display.py's take_screenshot/capture_for_model (same downscale, same
 * 0-1000 labeled grid, same JPEG/PNG output as base64).
 */
class ScreenCapture(private val context: Context) {

    data class Frame(
        val base64: String,
        val width: Int,          // captured image px (after downscale)
        val height: Int,
        val realW: Int,          // physical screen px
        val realH: Int,
        val mime: String,
    )

    private var projection: MediaProjection? = null
    private var reader: ImageReader? = null
    private var display: VirtualDisplay? = null
    private var handlerThread: HandlerThread? = null
    private var projectionTokenValid = false

    val isReady: Boolean get() = projection != null && projectionTokenValid

    /** Called by AgentService once it holds the granted MediaProjection. */
    fun start(resultCode: Int, data: android.content.Intent) {
        if (projection != null) return
        val mgr = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        handlerThread = HandlerThread("screen-capture").also { it.start() }
        val proj = mgr.getMediaProjection(resultCode, data)
        proj.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                projectionTokenValid = false
                Log.w("ScreenCapture", "MediaProjection stopped by system")
            }
        }, Handler(handlerThread!!.looper))
        projection = proj
        projectionTokenValid = true
        createVirtualDisplay()
    }

    private fun createVirtualDisplay() {
        val dm = context.resources.displayMetrics
        val w = dm.widthPixels
        val h = dm.heightPixels
        val dpi = dm.densityDpi
        reader?.close()
        reader = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2)
        display?.release()
        display = projection?.createVirtualDisplay(
            "agent-screen", w, h, dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader!!.surface, null, Handler(handlerThread!!.looper)
        )
    }

    fun stop() {
        try { display?.release() } catch (_: Exception) {}
        try { reader?.close() } catch (_: Exception) {}
        try { projection?.stop() } catch (_: Exception) {}
        display = null; reader = null; projection = null
        projectionTokenValid = false
        handlerThread?.quitSafely(); handlerThread = null
    }

    /**
     * Capture the screen, downscale to maxWidth (0 = keep real size), draw the
     * labeled 0-1000 grid, return base64. null when no frame is available yet.
     */
    fun capture(maxWidth: Int, jpegQuality: Int, grid: Boolean): Frame? {
        val r = reader ?: return null
        val image = try { r.acquireLatestImage() } catch (_: Exception) { null } ?: return null
        val bmp = try {
            val plane = image.planes[0]
            val rowStride = plane.rowStride
            val pixelStride = plane.pixelStride
            val width = image.width
            val height = image.height
            val padded = Bitmap.createBitmap(
                rowStride / pixelStride, height, Bitmap.Config.ARGB_8888)
            padded.copyPixelsFromBuffer(plane.buffer)
            Bitmap.createBitmap(padded, 0, 0, width, height)
        } finally {
            image.close()
        }

        val realW = bmp.width; val realH = bmp.height
        var out = bmp
        if (maxWidth > 0 && realW > maxWidth) {
            val nh = (realH.toFloat() / realW * maxWidth).roundToInt()
            out = Bitmap.createScaledBitmap(bmp, maxWidth, nh, true)
            bmp.recycle()
        }
        if (grid) out = drawGrid(out)
        val baos = ByteArrayOutputStream()
        val mime: String
        if (jpegQuality > 0) {
            out.compress(Bitmap.CompressFormat.JPEG, jpegQuality, baos); mime = "image/jpeg"
        } else {
            out.compress(Bitmap.CompressFormat.PNG, 100, baos); mime = "image/png"
        }
        val b64 = Base64.encodeToString(baos.toByteArray(), Base64.NO_WRAP)
        val fw = out.width; val fh = out.height
        out.recycle()
        return Frame(b64, fw, fh, realW, realH, mime)
    }

    /** Same look as display.py's _draw_grid: red lines, yellow 0-1000 labels. */
    private fun drawGrid(bmp: Bitmap): Bitmap {
        val w = bmp.width; val h = bmp.height
        val copy = bmp.copy(Bitmap.Config.ARGB_8888, true)
        bmp.recycle()
        val canvas = Canvas(copy)
        val small = w < 700
        val fs = if (small) 24f else 32f
        val step = if (small) 100 else 50
        val linePaint = Paint().apply {
            color = Color.argb(45, 255, 80, 80); strokeWidth = 1f; style = Paint.Style.STROKE
        }
        val textPaint = Paint().apply {
            color = Color.argb(230, 255, 210, 80); textSize = fs; isAntiAlias = true
            setShadowLayer(3f, 1f, 1f, Color.BLACK)
        }
        for (n in 0..1000 step step) {
            val px = n * w / 1000f
            canvas.drawLine(px, 0f, px, h.toFloat(), linePaint)
            if (n % 100 == 0) {
                val tx = minOf(px + 4, w - fs * 1.8f)
                canvas.drawText(n.toString(), tx, fs + 4, textPaint)
                canvas.drawText(n.toString(), tx, h - 8f, textPaint)
            }
        }
        for (n in 0..1000 step step) {
            val py = n * h / 1000f
            canvas.drawLine(0f, py, w.toFloat(), py, linePaint)
            if (n % 100 == 0) {
                val ty = minOf(py + fs + 4, h - 8f)
                canvas.drawText(n.toString(), 4f, ty, textPaint)
                canvas.drawText(n.toString(), w - fs * 1.8f, ty, textPaint)
            }
        }
        return copy
    }

    companion object {
        /** Activity-side: build the consent intent to show the user once. */
        fun consentIntent(context: Context) =
            (context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager)
                .createScreenCaptureIntent()
    }
}

package com.projet4.agentia.agent

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/**
 * Android equivalent of input_control.py — performs gestures and reads the UI.
 * The user must enable it once in system Settings → Accessibility.
 */
class AgentAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile var instance: AgentAccessibilityService? = null
            private set

        fun isEnabled(): Boolean = instance != null
    }

    override fun onServiceConnected() {
        instance = this
    }

    override fun onUnbind(intent: Intent?): Boolean {
        instance = null
        return super.onUnbind(intent)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}

    // ------------------------------------------------------------ gestures
    private fun dispatchPath(path: Path, durationMs: Long, willContinue: Boolean = false): Boolean {
        val latch = CountDownLatch(1)
        var ok = false
        val stroke = GestureDescription.StrokeDescription(path, 0L, durationMs, willContinue)
        val desc = GestureDescription.Builder().addStroke(stroke).build()
        val dispatched = dispatchGesture(desc, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) { ok = true; latch.countDown() }
            override fun onCancelled(gestureDescription: GestureDescription?) { latch.countDown() }
        }, null)
        if (!dispatched) return false
        latch.await(durationMs + 3000, TimeUnit.MILLISECONDS)
        return ok
    }

    fun tap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        return dispatchPath(path, 80L)
    }

    fun doubleTap(x: Float, y: Float): Boolean {
        val a = tap(x, y)
        Thread.sleep(120)
        val b = tap(x, y)
        return a && b
    }

    fun longPress(x: Float, y: Float, durationMs: Long = 800): Boolean {
        // a stroke that goes down and holds = long press
        val path = Path().apply { moveTo(x, y); lineTo(x + 0.5f, y + 0.5f) }
        return dispatchPath(path, durationMs.coerceIn(300, 5000))
    }

    fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long = 350): Boolean {
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        return dispatchPath(path, durationMs.coerceIn(80, 2500))
    }

    fun scroll(direction: String, amount: Float = 0.6f): Boolean {
        val dm = resources.displayMetrics
        val cx = dm.widthPixels / 2f
        val cy = dm.heightPixels / 2f
        val dy = dm.heightPixels * amount * 0.5f
        return when (direction.lowercase()) {
            "down" -> swipe(cx, cy - dy / 2, cx, cy + dy / 2)
            "up" -> swipe(cx, cy + dy / 2, cx, cy - dy / 2)
            "left" -> swipe(cx + dm.widthPixels * amount / 2, cy, cx - dm.widthPixels * amount / 2, cy)
            "right" -> swipe(cx - dm.widthPixels * amount / 2, cy, cx + dm.widthPixels * amount / 2, cy)
            else -> swipe(cx, cy + dy / 2, cx, cy - dy / 2)
        }
    }

    // ------------------------------------------------------------ global
    fun global(name: String): Boolean = when (name.lowercase()) {
        "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
        "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
        "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
        "notifications" -> performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
        "quick_settings" -> performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
        "power_dialog" -> performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
        else -> false
    }

    // ------------------------------------------------------------ text input
    /** Type text into the focused editable node, or the first editable one. */
    fun typeText(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val editable = findEditable(root)
        if (editable != null) {
            // focus it first
            editable.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            val args = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
            }
            val ok = editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            editable.recycle()
            if (ok) return true
        }
        // fallback: clipboard paste into focused node
        val focused = findFocused(root)
        if (focused != null) {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("agent", text))
            focused.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            val ok = focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            focused.recycle()
            return ok
        }
        return false
    }

    fun pressEnter(): Boolean {
        val root = rootInActiveWindow ?: return false
        val editable = findEditable(root) ?: findFocused(root) ?: return false
        val ok = if (Build.VERSION.SDK_INT >= 30) {
            editable.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)
        } else false
        editable.recycle()
        return ok
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable && node.isVisibleToUser) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditable(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    private fun findFocused(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        return node.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
    }

    /** Click the node closest to normalized coords — used when a gesture tap misses. */
    fun clickNodeAt(normX: Float, normY: Float): Boolean {
        val root = rootInActiveWindow ?: return false
        val dm = resources.displayMetrics
        val px = normX / 1000f * dm.widthPixels
        val py = normY / 1000f * dm.heightPixels
        val node = deepestClickableAt(root, px, py)
        return node?.let {
            val ok = it.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            it.recycle(); ok
        } ?: false
    }

    private fun deepestClickableAt(node: AccessibilityNodeInfo, x: Float, y: Float): AccessibilityNodeInfo? {
        val r = Rect()
        node.getBoundsInScreen(r)
        if (!r.contains(x.toInt(), y.toInt())) return null
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val hit = deepestClickableAt(child, x, y)
            if (hit != null) { child.recycle(); return hit }
            child.recycle()
        }
        // walk up to the nearest clickable ancestor
        var current = AccessibilityNodeInfo.obtain(node)
        var candidate: AccessibilityNodeInfo? = if (node.isClickable) current else null
        var p = node.parent
        while (p != null) {
            if (p.isClickable && candidate == null) {
                candidate = AccessibilityNodeInfo.obtain(p)
            }
            val np = p.parent
            p.recycle()
            p = np
        }
        return candidate
    }

    // ------------------------------------------------------------ UI tree
    /**
     * Serialize the visible UI tree to compact text — the Android superpower
     * the desktop version lacks. Each line: class, text, bounds in 0-1000 coords.
     */
    fun dumpUiTree(maxNodes: Int = 350): String {
        val root = rootInActiveWindow ?: return ""
        val dm = resources.displayMetrics
        val sb = StringBuilder()
        var count = 0
        fun walk(node: AccessibilityNodeInfo, depth: Int) {
            if (count >= maxNodes || depth > 14) return
            val r = Rect(); node.getBoundsInScreen(r)
            if (node.isVisibleToUser && !r.isEmpty) {
                val text = (node.text ?: node.contentDescription ?: "").toString()
                    .replace("\n", " ").take(80)
                val cls = node.className?.toString()?.substringAfterLast('.') ?: "?"
                if (text.isNotEmpty() || node.isClickable || node.isEditable || node.isScrollable) {
                    val nx1 = (r.left * 1000 / dm.widthPixels)
                    val ny1 = (r.top * 1000 / dm.heightPixels)
                    val nx2 = (r.right * 1000 / dm.widthPixels)
                    val ny2 = (r.bottom * 1000 / dm.heightPixels)
                    val flags = buildString {
                        if (node.isClickable) append(",click")
                        if (node.isEditable) append(",edit")
                        if (node.isScrollable) append(",scroll")
                    }
                    sb.append("  ".repeat(minOf(depth, 6)))
                        .append("$cls[$nx1,$ny1-$nx2,$ny2$flags]")
                        .append(if (text.isNotEmpty()) " \"$text\"" else "")
                        .append("\n")
                    count++
                }
            }
            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                walk(child, depth + 1)
                child.recycle()
            }
        }
        walk(root, 0)
        return sb.toString().take(6000)
    }

    fun currentAppPackage(): String {
        return rootInActiveWindow?.packageName?.toString() ?: ""
    }
}

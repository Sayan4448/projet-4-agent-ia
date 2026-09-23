package com.projet4.agentia.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.projet4.agentia.R
import com.projet4.agentia.data.RunHistoryStore
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Foreground service owning the MediaProjection and running one AgentRun at a
 * time — the Android counterpart of agent.py's single-owner rule.
 */
class AgentService : Service() {

    companion object {
        const val CHANNEL_ID = "agent_run"
        const val NOTIF_ID = 42
        const val ACTION_STOP = "com.projet4.agentia.STOP"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val EXTRA_GOAL = "goal"

        // UI-facing live state
        val running = MutableStateFlow(false)
        val events = MutableSharedFlow<Pair<String, Map<String, Any?>>>(extraBufferCapacity = 200)
        val lastResult = MutableStateFlow<Map<String, Any?>?>(null)

        @Volatile var activeService: AgentService? = null
            private set
    }

    inner class LocalBinder : Binder() {
        fun getService(): AgentService = this@AgentService
    }

    private val binder = LocalBinder()
    private var capture: ScreenCapture? = null
    private var run: AgentRun? = null
    private var executor: ExecutorService? = null
    private var runRecord: RunHistoryStore.RunRecord? = null
    private var overlay: OverlayIndicator? = null

    override fun onBind(intent: Intent): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        RunHistoryStore.init(this)
        createChannel()
    }

    private fun createChannel() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel(
            CHANNEL_ID, getString(R.string.channel_agent), NotificationManager.IMPORTANCE_LOW
        ).apply { description = getString(R.string.channel_agent_desc) })
    }

    private fun buildNotification(text: String): Notification {
        val stopIntent = PendingIntent.getService(
            this, 0, Intent(this, AgentService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val openIntent = PendingIntent.getActivity(
            this, 1, packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(getString(R.string.notif_agent_running))
            .setContentText(text)
            .setContentIntent(openIntent)
            .addAction(android.R.drawable.ic_media_pause, getString(R.string.stop), stopIntent)
            .setOngoing(true)
            .build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            run?.stop()
            return START_NOT_STICKY
        }
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        val data = intent?.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
        val goal = intent?.getStringExtra(EXTRA_GOAL) ?: ""
        if (resultCode == Int.MIN_VALUE || data == null || goal.isEmpty()) {
            stopSelf(); return START_NOT_STICKY
        }
        if (running.value) return START_NOT_STICKY

        // startForeground must happen BEFORE getMediaProjection on API 29+
        val notif = buildNotification(goal.take(80))
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIF_ID, notif)
        }

        capture = ScreenCapture(this).also { it.start(resultCode, data) }
        overlay = OverlayIndicator(this)
        running.value = true
        activeService = this
        runRecord = RunHistoryStore.RunRecord(goal = goal).also { RunHistoryStore.save(it) }

        executor = Executors.newSingleThreadExecutor()
        executor!!.submit {
            val r = AgentRun(this, goal, capture!!) { event, data -> onEvent(event, data) }
            run = r
            val result = try {
                r.run()
            } catch (e: Exception) {
                mapOf("outcome" to "error", "summary" to (e.message ?: "crash"),
                      "steps" to r.currentStep, "provider" to r.effectiveProvider)
            }
            finishRun(result)
        }
        return START_STICKY
    }

    private fun onEvent(event: String, data: Map<String, Any?>) {
        events.tryEmit(event to data)
        val line = when (event) {
            "step" -> "étape ${data["step"]}: ${data["actions"]}"
            "action_result" -> "  → ${data["result"]}"
            "agent_message" -> "agent: ${data["text"]}"
            "fallback" -> "fallback ${data["from"]}→${data["to"]}: ${data["reason"]}"
            "error" -> "erreur: ${data["message"]}"
            "guidance" -> "guidance: ${data["text"]}"
            else -> null
        }
        line?.let { runRecord?.log?.add(it) }
        if (event == "cursor") {
            val x = (data["x"] as? Number)?.toFloat() ?: return
            val y = (data["y"] as? Number)?.toFloat() ?: return
            overlay?.flash(x, y)
        }
        if (event == "step") {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify(NOTIF_ID, buildNotification("Étape ${data["step"]} — ${data["actions"]}".take(80)))
        }
    }

    private fun finishRun(result: Map<String, Any?>) {
        runRecord?.apply {
            finishedAt = System.currentTimeMillis()
            outcome = result["outcome"]?.toString() ?: "unknown"
            summary = result["summary"]?.toString() ?: ""
            provider = result["provider"]?.toString() ?: ""
            RunHistoryStore.save(this)
        }
        running.value = false
        lastResult.value = result
        activeService = null
        capture?.stop(); capture = null
        overlay?.remove(); overlay = null
        run = null
        executor?.shutdown(); executor = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    fun stopRun() { run?.stop() }

    fun guide(text: String) { run?.guide(text) }

    fun screenshotNow(maxWidth: Int, jpegQuality: Int, grid: Boolean) =
        capture?.capture(maxWidth, jpegQuality, grid)

    override fun onDestroy() {
        run?.stop()
        capture?.stop()
        overlay?.remove()
        running.value = false
        activeService = null
        super.onDestroy()
    }
}

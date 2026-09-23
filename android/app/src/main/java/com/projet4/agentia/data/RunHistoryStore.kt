package com.projet4.agentia.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * Port of sessions.py — every agent run is recorded (goal, outcome, log) and
 * replayable from the History tab.
 */
object RunHistoryStore {
    data class RunRecord(
        val id: String = UUID.randomUUID().toString().replace("-", ""),
        val goal: String,
        val startedAt: Long = System.currentTimeMillis(),
        var finishedAt: Long = 0,
        var outcome: String = "running",
        var summary: String = "",
        var provider: String = "",
        val log: MutableList<String> = mutableListOf(),
    )

    private lateinit var file: File
    private const val MAX_RUNS = 100

    fun init(context: Context) {
        file = File(context.filesDir, "runs.json")
    }

    @Synchronized
    fun loadAll(): List<RunRecord> {
        if (!::file.isInitialized || !file.isFile) return emptyList()
        return try {
            val raw = JSONArray(file.readText(Charsets.UTF_8))
            (0 until raw.length()).mapNotNull { i ->
                val o = raw.optJSONObject(i) ?: return@mapNotNull null
                val logArr = o.optJSONArray("log") ?: JSONArray()
                RunRecord(
                    id = o.optString("id"),
                    goal = o.optString("goal"),
                    startedAt = o.optLong("started_at"),
                    finishedAt = o.optLong("finished_at"),
                    outcome = o.optString("outcome", "unknown"),
                    summary = o.optString("summary"),
                    provider = o.optString("provider"),
                    log = (0 until logArr.length()).map { logArr.optString(it) }.toMutableList(),
                )
            }.sortedByDescending { it.startedAt }
        } catch (_: Exception) { emptyList() }
    }

    @Synchronized
    fun save(run: RunRecord) {
        val items = (loadAll().filter { it.id != run.id } + run)
            .sortedByDescending { it.startedAt }.take(MAX_RUNS)
        val arr = JSONArray()
        for (r in items) {
            arr.put(JSONObject()
                .put("id", r.id).put("goal", r.goal.take(300))
                .put("started_at", r.startedAt).put("finished_at", r.finishedAt)
                .put("outcome", r.outcome).put("summary", r.summary.take(2000))
                .put("provider", r.provider)
                .put("log", JSONArray(r.log.map { it.take(500) })))
        }
        val tmp = File(file.parentFile, ".runs.tmp")
        tmp.writeText(arr.toString(2), Charsets.UTF_8)
        tmp.renameTo(file)
    }
}

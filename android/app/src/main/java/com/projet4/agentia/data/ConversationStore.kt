package com.projet4.agentia.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * Port of conversations.py — local, atomic conversation store.
 * Favorites on top, then most recent; titles derived locally (no AI call).
 */
object ConversationStore {
    private const val MAX_TEXT = 30000

    data class Message(val role: String, val text: String, val provider: String = "")
    data class Conversation(
        val id: String = UUID.randomUUID().toString().replace("-", ""),
        var title: String = "Nouvelle discussion",
        var favorite: Boolean = false,
        var updated: Double = System.currentTimeMillis() / 1000.0,
        val messages: MutableList<Message> = mutableListOf(),
    )

    private lateinit var file: File

    fun init(context: Context) {
        file = File(context.filesDir, "conversations.json")
    }

    @Synchronized
    fun loadAll(): List<Conversation> {
        if (!::file.isInitialized || !file.isFile) return emptyList()
        return try {
            val raw = JSONArray(file.readText(Charsets.UTF_8))
            (0 until raw.length()).mapNotNull { i ->
                val o = raw.optJSONObject(i) ?: return@mapNotNull null
                val msgs = o.optJSONArray("messages") ?: JSONArray()
                Conversation(
                    id = o.optString("id").ifEmpty { UUID.randomUUID().toString() },
                    title = o.optString("title", "Nouvelle discussion").take(80),
                    favorite = o.optBoolean("favorite", false),
                    updated = o.optDouble("updated", 0.0),
                    messages = (0 until msgs.length()).mapNotNull { j ->
                        val m = msgs.optJSONObject(j) ?: return@mapNotNull null
                        val role = m.optString("role")
                        if (role in listOf("user", "assistant"))
                            Message(role, m.optString("text").take(MAX_TEXT),
                                m.optString("provider").take(30))
                        else null
                    }.toMutableList(),
                )
            }.sortedWith(compareBy({ !it.favorite }, { -it.updated }))
        } catch (_: Exception) { emptyList() }
    }

    @Synchronized
    fun save(conv: Conversation): Conversation {
        conv.updated = System.currentTimeMillis() / 1000.0
        val items = loadAll().filter { it.id != conv.id } + conv
        persist(items.sortedWith(compareBy({ !it.favorite }, { -it.updated })))
        return conv
    }

    @Synchronized
    fun delete(id: String) = persist(loadAll().filter { it.id != id })

    private fun persist(items: List<Conversation>) {
        val arr = JSONArray()
        for (c in items) {
            val msgs = JSONArray()
            for (m in c.messages) {
                msgs.put(JSONObject().put("role", m.role).put("text", m.text)
                    .put("provider", m.provider))
            }
            arr.put(JSONObject().put("id", c.id).put("title", c.title)
                .put("favorite", c.favorite).put("updated", c.updated)
                .put("messages", msgs))
        }
        val tmp = File(file.parentFile, ".conversations.tmp")
        tmp.writeText(arr.toString(2), Charsets.UTF_8)
        tmp.renameTo(file)
    }

    /** Free title derived locally — same rule as title_from(). */
    fun titleFrom(text: String): String {
        val oneLine = text.trim().replace(Regex("\\s+"), " ")
        return if (oneLine.length > 48) oneLine.take(47) + "…"
        else oneLine.ifEmpty { "Nouvelle discussion" }
    }
}

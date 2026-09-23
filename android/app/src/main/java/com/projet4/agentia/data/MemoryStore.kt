package com.projet4.agentia.data

import android.content.Context
import org.json.JSONArray
import java.io.File

/**
 * Port of memory.py — explicit user preferences shared between Chat and Agent.
 * Stored as a JSON list of strings.
 */
object MemoryStore {
    private lateinit var file: File

    fun init(context: Context) {
        file = File(context.filesDir, "memory.json")
    }

    @Synchronized
    fun list(): MutableList<String> {
        if (!::file.isInitialized || !file.isFile) return mutableListOf()
        return try {
            val arr = JSONArray(file.readText(Charsets.UTF_8))
            MutableList(arr.length()) { arr.getString(it) }
        } catch (_: Exception) { mutableListOf() }
    }

    @Synchronized
    fun add(fact: String) {
        val items = list()
        val t = fact.trim()
        if (t.isNotEmpty() && t !in items) {
            items.add(t.take(200))
            persist(items)
        }
    }

    @Synchronized
    fun removeAt(index: Int) {
        val items = list()
        if (index in items.indices) {
            items.removeAt(index)
            persist(items)
        }
    }

    @Synchronized
    fun clear() = persist(mutableListOf())

    private fun persist(items: List<String>) {
        file.writeText(JSONArray(items).toString(2), Charsets.UTF_8)
    }

    /** The text block appended to prompts — same role as memory.prompt_block(). */
    fun promptBlock(context: Context): String {
        if (!::file.isInitialized) init(context)
        val items = list()
        if (items.isEmpty()) return ""
        return " User preferences to respect: " + items.joinToString(" | ") + "."
    }
}

package com.projet4.agentia.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Port of agent_screen/settings.py — config persisted as JSON in app files.
 * Same provider list, same defaults, same merge semantics.
 */
object SettingsStore {

    val LOCAL_PROVIDERS = listOf("ollama", "lmstudio")
    val PROVIDERS = listOf("gemini", "openai", "anthropic", "groq", "deepseek", "openrouter") + LOCAL_PROVIDERS

    val PROVIDER_NAMES = mapOf(
        "gemini" to "Google Gemini",
        "openai" to "OpenAI",
        "anthropic" to "Anthropic (Claude)",
        "groq" to "Groq",
        "deepseek" to "DeepSeek",
        "openrouter" to "OpenRouter",
        "ollama" to "Ollama (local)",
        "lmstudio" to "LM Studio (local)",
    )

    val DEFAULT_MODELS = mapOf(
        "gemini" to "gemini-3.5-flash",
        "openai" to "gpt-4.1-mini",
        "anthropic" to "claude-sonnet-4-5",
        "groq" to "meta-llama/llama-4-scout-17b-16e-instruct",
        "deepseek" to "deepseek-chat",
        "openrouter" to "google/gemini-2.5-flash",
        "ollama" to "",
        "lmstudio" to "",
    )

    private fun defaults() = mutableMapOf<String, Any?>(
        "provider" to "gemini",
        "api_keys" to PROVIDERS.associateWith { "" }.toMutableMap(),
        "models" to DEFAULT_MODELS.toMutableMap(),
        "models_available" to mutableMapOf<String, List<String>>(),
        "local_urls" to mutableMapOf("ollama" to "http://127.0.0.1:11434", "lmstudio" to "http://127.0.0.1:1234/v1"),
        "max_steps" to 20,
        "grid" to true,
        "image_width" to 1280,
        "step_delay" to 0.4,
        "jpeg_quality" to 80,
        "eco_mode" to false,
        "limit_actions_per_capture" to true,
        "actions_per_capture" to 3,
        "language" to "fr",
        "accent" to "violet",
        "memory_enabled" to true,
        "chat_eco" to true,
        "chat_context_messages" to 6,
        "chat_response_tokens" to 700,
        "ai_timeout" to 45,
        // Android bonus: feed the accessibility node tree to the model
        "ui_tree_enabled" to true,
    )

    private var cfg: MutableMap<String, Any?>? = null
    private lateinit var file: File

    fun init(context: Context) {
        file = File(context.filesDir, "config.json")
    }

    @Suppress("UNCHECKED_CAST")
    private fun mergeInto(base: MutableMap<String, Any?>, stored: JSONObject) {
        for (key in stored.keys()) {
            val v = stored.get(key)
            val cur = base[key]
            if (cur is MutableMap<*, *> && v is JSONObject) {
                val map = cur as MutableMap<String, Any?>
                for (k in v.keys()) map[k] = v.get(k)
            } else if (v != JSONObject.NULL) {
                base[key] = v
            }
        }
    }

    @Synchronized
    fun load(): MutableMap<String, Any?> {
        cfg?.let { return it }
        val base = defaults()
        if (::file.isInitialized && file.isFile) {
            try {
                val stored = JSONObject(file.readText(Charsets.UTF_8))
                mergeInto(base, stored)
            } catch (_: Exception) {
                // damaged config is preserved, never overwritten (same rule as the desktop app)
            }
        }
        cfg = base
        return base
    }

    @Synchronized
    @Suppress("UNCHECKED_CAST")
    fun save(partial: Map<String, Any?>): MutableMap<String, Any?> {
        val c = load()
        for ((k, v) in partial) {
            val cur = c[k]
            if (cur is MutableMap<*, *> && v is Map<*, *>) {
                val map = cur as MutableMap<String, Any?>
                for ((mk, mv) in v) map[mk.toString()] = mv
            } else {
                c[k] = v
            }
        }
        // coerce numerics like the Python version does
        c["max_steps"] = (c["max_steps"] as? Number)?.toInt()?.coerceIn(1, 40) ?: 20
        c["actions_per_capture"] = (c["actions_per_capture"] as? Number)?.toInt()?.coerceIn(1, 3) ?: 3
        c["image_width"] = (c["image_width"] as? Number)?.toInt()?.coerceIn(0, 2560) ?: 1280
        c["jpeg_quality"] = (c["jpeg_quality"] as? Number)?.toInt()?.coerceIn(0, 95) ?: 80
        c["ai_timeout"] = (c["ai_timeout"] as? Number)?.toInt()?.coerceIn(10, 180) ?: 45
        c["chat_context_messages"] = (c["chat_context_messages"] as? Number)?.toInt()?.coerceIn(0, 20) ?: 6
        c["chat_response_tokens"] = (c["chat_response_tokens"] as? Number)?.toInt()?.coerceIn(128, 4096) ?: 700
        persist(c)
        return c
    }

    private fun persist(c: Map<String, Any?>) {
        val tmp = File(file.parentFile, ".config.tmp")
        tmp.writeText(toJson(c).toString(2), Charsets.UTF_8)
        tmp.renameTo(file)
    }

    @Suppress("UNCHECKED_CAST")
    private fun toJson(m: Map<String, Any?>): JSONObject {
        val o = JSONObject()
        for ((k, v) in m) {
            o.put(k, when (v) {
                is Map<*, *> -> toJson(v as Map<String, Any?>)
                is List<*> -> JSONArray(v)
                null -> JSONObject.NULL
                else -> v
            })
        }
        return o
    }

    fun splitKeys(raw: String): List<String> =
        raw.split(Regex("[,;\\s]+")).map { it.trim().trim('"', '\'') }
            .filter { it.length >= 4 }.distinct()

    fun getProviderKeys(provider: String): List<String> {
        @Suppress("UNCHECKED_CAST")
        val keys = (load()["api_keys"] as? Map<String, String>) ?: return emptyList()
        return splitKeys(keys[provider] ?: "")
    }

    fun getApiKey(provider: String): String = getProviderKeys(provider).firstOrNull() ?: ""

    fun getModel(provider: String): String {
        @Suppress("UNCHECKED_CAST")
        val models = load()["models"] as? Map<String, String> ?: return ""
        return models[provider] ?: ""
    }

    fun getLocalUrl(provider: String): String {
        @Suppress("UNCHECKED_CAST")
        val urls = load()["local_urls"] as? Map<String, String> ?: return ""
        return (urls[provider] ?: "").trimEnd('/')
    }

    fun availableProviders(): List<String> =
        PROVIDERS.filter { it in LOCAL_PROVIDERS || getProviderKeys(it).isNotEmpty() }

    fun str(key: String, fallback: String = ""): String = (load()[key] as? String) ?: fallback
    fun bool(key: String, fallback: Boolean = false): Boolean = (load()[key] as? Boolean) ?: fallback
    fun int(key: String, fallback: Int = 0): Int = (load()[key] as? Number)?.toInt() ?: fallback
    fun dbl(key: String, fallback: Double = 0.0): Double = (load()[key] as? Number)?.toDouble() ?: fallback
}

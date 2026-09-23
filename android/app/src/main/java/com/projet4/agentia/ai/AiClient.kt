package com.projet4.agentia.ai

import com.projet4.agentia.data.SettingsStore
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Port of agent_screen/ai_client.py — unified multi-provider chat client
 * (image-capable). Providers: Gemini, OpenAI, Anthropic, Groq, DeepSeek,
 * OpenRouter + local Ollama / LM Studio.
 */
object AiClient {

    class AIError(message: String) : Exception(message)

    private val ENDPOINTS = mapOf(
        "openai" to "https://api.openai.com/v1/chat/completions",
        "groq" to "https://api.groq.com/openai/v1/chat/completions",
        "deepseek" to "https://api.deepseek.com/chat/completions",
        "openrouter" to "https://openrouter.ai/api/v1/chat/completions",
        "anthropic" to "https://api.anthropic.com/v1/messages",
        "gemini" to "https://generativelanguage.googleapis.com/v1beta/models",
    )

    private const val SAFE_MAX_TOKENS = 1024
    private const val FAILED_KEYS_COOLDOWN_MS = 90_000L

    private val failedKeys = mutableMapOf<String, Long>()

    private fun client(): OkHttpClient {
        val timeout = SettingsStore.int("ai_timeout", 45).coerceIn(10, 180).toLong()
        return OkHttpClient.Builder()
            .connectTimeout(timeout, TimeUnit.SECONDS)
            .readTimeout(timeout, TimeUnit.SECONDS)
            .writeTimeout(timeout, TimeUnit.SECONDS)
            .build()
    }

    private fun providerName(p: String) = SettingsStore.PROVIDER_NAMES[p] ?: p

    // ------------------------------------------------------- error wording
    private fun explainHttp(provider: String, status: Int, text: String): String {
        val name = providerName(provider)
        val t = (text).take(600)
        val low = t.lowercase()
        fun first(vararg patterns: String): String {
            for (pat in patterns) {
                val m = Regex(pat).find(t)
                if (m != null && m.groupValues.size > 1) return m.groupValues[1].take(200)
            }
            return ""
        }
        return when {
            status == 401 || status == 403 -> {
                val detail = first("\"message\"\\s*:\\s*\"([^\"]+)\"", "\"error_message\"\\s*:\\s*\"([^\"]+)\"")
                var base = "Clé API $name refusée ($status). "
                base += when {
                    "expired" in low || "revoked" in low ->
                        "La clé semble expirée ou révoquée — recrée-la sur le site du fournisseur."
                    "quota" in low || "billing" in low || "credit" in low ->
                        "Problème de quota/facturation sur le compte du fournisseur."
                    else -> "Vérifie la clé dans Paramètres (sans espaces, complète)."
                }
                if (detail.isNotEmpty()) base += "  [$detail]"
                base
            }
            status == 404 -> {
                val d = first("\"message\"\\s*:\\s*\"([^\"]+)\"")
                "Modèle introuvable chez $name (404). Choisis un autre modèle dans le sélecteur.  [$d]"
            }
            status == 429 ->
                "Limite de requêtes/quota atteinte chez $name (429). Attends un peu, ou utilise un autre fournisseur."
            status >= 500 ->
                "Les serveurs $name sont surchargés ou en panne ($status). C'est temporaire — l'agent réessaie déjà automatiquement."
            else -> {
                val d = first("\"message\"\\s*:\\s*\"([^\"]+)\"", "\"error\"\\s*:\\s*\"([^\"]+)\"")
                "Erreur $name ($status): ${d.ifEmpty { t.take(200) }}"
            }
        }
    }

    private fun networkError(e: IOException) = AIError(
        "Pas de connexion internet (ou réseau bloqué). Vérifie ta connexion puis réessaie. [${e.javaClass.simpleName}]"
    )

    // ------------------------------------------------------- http helpers
    private fun post(url: String, headers: Map<String, String>, body: JSONObject, retry5xx: Int = 2): okhttp3.Response {
        var delayMs = 3000L
        var attempt = 0
        while (true) {
            val req = Request.Builder().url(url)
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .apply { headers.forEach { (k, v) -> addHeader(k, v) } }
                .build()
            val r = try {
                client().newCall(req).execute()
            } catch (e: IOException) {
                throw networkError(e)
            }
            if (r.code < 500 || attempt >= retry5xx) return r
            r.close()
            Thread.sleep(delayMs)
            delayMs *= 2
            attempt++
        }
    }

    private fun get(url: String, headers: Map<String, String>): okhttp3.Response {
        val req = Request.Builder().url(url).get()
            .apply { headers.forEach { (k, v) -> addHeader(k, v) } }
            .build()
        return try {
            client().newCall(req).execute()
        } catch (e: IOException) {
            throw networkError(e)
        }
    }

    // ------------------------------------------------------- media helpers
    data class Media(val data: String, val mime: String)

    private fun normalizeMedia(media: Any?, fallbackMime: String = "image/png"): List<Media> {
        if (media == null) return emptyList()
        if (media is String) return listOf(Media(media, fallbackMime))
        @Suppress("UNCHECKED_CAST")
        return (media as? List<Any>)?.take(4)?.mapNotNull { item ->
            when (item) {
                is String -> Media(item, fallbackMime)
                is Media -> item
                is List<*> -> Media(item[0].toString(), (item.getOrNull(1) as? String) ?: fallbackMime)
                else -> null
            }
        } ?: emptyList()
    }

    // ------------------------------------------------------- provider calls
    private fun callOpenAiStyle(provider: String, key: String, model: String, system: String,
                                prompt: String, media: Any?, isJson: Boolean,
                                maxTokens: Int = 2048, mime: String = "image/png"): String {
        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", system))
        val mediaList = normalizeMedia(media, mime)
        if (mediaList.isNotEmpty()) {
            val content = JSONArray()
            content.put(JSONObject().put("type", "text").put("text", prompt))
            for (m in mediaList) {
                content.put(JSONObject().put("type", "image_url")
                    .put("image_url", JSONObject().put("url", "data:${m.mime};base64,${m.data}")))
            }
            messages.put(JSONObject().put("role", "user").put("content", content))
        } else {
            messages.put(JSONObject().put("role", "user").put("content", prompt))
        }
        val body = JSONObject()
            .put("model", model).put("messages", messages)
            .put("temperature", 0.2).put("max_tokens", maxTokens)
        if (isJson) body.put("response_format", JSONObject().put("type", "json_object"))

        var r = post(ENDPOINTS.getValue(provider),
            mapOf("Authorization" to "Bearer $key", "Content-Type" to "application/json"), body)

        if (r.code >= 400) {
            if (r.code in listOf(400, 422) && maxTokens != SAFE_MAX_TOKENS) {
                r.close()
                return callOpenAiStyle(provider, key, model, system, prompt, media,
                    isJson, SAFE_MAX_TOKENS, mime)
            }
            if (r.code in listOf(400, 422) && isJson) {
                body.remove("response_format")
                r.close()
                val r2 = post(ENDPOINTS.getValue(provider),
                    mapOf("Authorization" to "Bearer $key", "Content-Type" to "application/json"), body)
                if (r2.code < 400) {
                    val out = extractOpenAiContent(JSONObject(r2.body!!.string()))
                    r2.close()
                    return out
                }
                r = r2
            }
            val errText = r.body?.string() ?: ""
            r.close()
            throw AIError(explainHttp(provider, r.code, errText))
        }
        val data = JSONObject(r.body!!.string()); r.close()
        return extractOpenAiContent(data)
    }

    private fun extractOpenAiContent(data: JSONObject): String {
        val choice = data.optJSONArray("choices")?.optJSONObject(0) ?: return ""
        val msg = choice.optJSONObject("message") ?: return ""
        return when (val content = msg.opt("content")) {
            is JSONArray -> buildString {
                for (i in 0 until content.length()) {
                    val b = content.optJSONObject(i) ?: continue
                    append(b.optString("text", ""))
                }
            }
            is String -> content
            else -> ""
        }.trim()
    }

    private fun callAnthropic(key: String, model: String, system: String,
                              prompt: String, media: Any?, isJson: Boolean,
                              maxTokens: Int = 2048, mime: String = "image/png"): String {
        val content = JSONArray()
        for (m in normalizeMedia(media, mime)) {
            content.put(JSONObject().put("type", "image")
                .put("source", JSONObject().put("type", "base64")
                    .put("media_type", m.mime).put("data", m.data)))
        }
        content.put(JSONObject().put("type", "text").put("text", prompt))
        val body = JSONObject()
            .put("model", model).put("max_tokens", maxTokens).put("system", system)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", content)))
        val r = post(ENDPOINTS.getValue("anthropic"),
            mapOf("x-api-key" to key, "anthropic-version" to "2023-06-01",
                "Content-Type" to "application/json"), body)
        if (r.code >= 400) {
            if (r.code in listOf(400, 422) && maxTokens != SAFE_MAX_TOKENS) {
                r.close()
                return callAnthropic(key, model, system, prompt, media, isJson, SAFE_MAX_TOKENS, mime)
            }
            val errText = r.body?.string() ?: ""; r.close()
            throw AIError(explainHttp("anthropic", r.code, errText))
        }
        val data = JSONObject(r.body!!.string()); r.close()
        val blocks = data.optJSONArray("content") ?: return ""
        return buildString {
            for (i in 0 until blocks.length()) append(blocks.optJSONObject(i)?.optString("text", "") ?: "")
        }.trim()
    }

    private fun healDeprecatedGeminiModel(key: String, failedModel: String, errorText: String): String? {
        val m = Regex("models/([A-Za-z0-9.\\-]+)").find(errorText) ?: return null
        val suggestion = m.groupValues[1]
        if (suggestion == failedModel) return null
        return try {
            val r = get("${ENDPOINTS.getValue("gemini")}/$suggestion?key=$key", emptyMap())
            val ok = r.code < 400; r.close()
            if (ok) {
                SettingsStore.save(mapOf("models" to mapOf("gemini" to suggestion)))
                suggestion
            } else null
        } catch (_: Exception) { null }
    }

    private fun callGemini(key: String, model: String, system: String,
                           prompt: String, media: Any?, isJson: Boolean,
                           maxTokens: Int = 2048, mime: String = "image/png"): String {
        val parts = JSONArray()
        for (m in normalizeMedia(media, mime)) {
            parts.put(JSONObject().put("inline_data",
                JSONObject().put("mime_type", m.mime).put("data", m.data)))
        }
        parts.put(JSONObject().put("text", prompt))
        val genCfg = JSONObject().put("temperature", 0.2).put("maxOutputTokens", maxTokens)
        if (isJson) genCfg.put("responseMimeType", "application/json")
        val body = JSONObject()
            .put("system_instruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", system))))
            .put("contents", JSONArray().put(JSONObject().put("role", "user").put("parts", parts)))
            .put("generationConfig", genCfg)
        val url = "${ENDPOINTS.getValue("gemini")}/$model:generateContent?key=$key"
        val r = post(url, mapOf("Content-Type" to "application/json"), body)
        if (r.code >= 400) {
            if (r.code in listOf(400, 422) && maxTokens != SAFE_MAX_TOKENS) {
                r.close()
                return callGemini(key, model, system, prompt, media, isJson, SAFE_MAX_TOKENS, mime)
            }
            val errText = r.body?.string() ?: ""
            if (r.code == 404) {
                healDeprecatedGeminiModel(key, model, errText)?.let { healed ->
                    r.close()
                    return callGemini(key, healed, system, prompt, media, isJson, maxTokens, mime)
                }
            }
            r.close()
            throw AIError(explainHttp("gemini", r.code, errText))
        }
        val data = JSONObject(r.body!!.string()); r.close()
        val cands = data.optJSONArray("candidates") ?: return ""
        val cparts = cands.optJSONObject(0)?.optJSONObject("content")?.optJSONArray("parts") ?: return ""
        return buildString {
            for (i in 0 until cparts.length()) append(cparts.optJSONObject(i)?.optString("text", "") ?: "")
        }.trim()
    }

    private fun localBase(provider: String): String {
        val base = SettingsStore.getLocalUrl(provider)
        return if (provider == "ollama") base.removeSuffix("/api").removeSuffix("/v1")
        else if (base.endsWith("/v1")) base else "$base/v1"
    }

    private fun callLocal(provider: String, key: String, model: String, system: String,
                          prompt: String, media: Any?, isJson: Boolean,
                          mime: String, maxTokens: Int): String {
        val headers = mutableMapOf("Content-Type" to "application/json")
        if (key.isNotEmpty()) headers["Authorization"] = "Bearer $key"
        val mediaList = normalizeMedia(media, mime)
        val user = JSONObject().put("role", "user")
        val body = JSONObject().put("model", model).put("stream", false)
        val url: String
        if (provider == "ollama") {
            user.put("content", prompt)
            if (mediaList.isNotEmpty()) {
                user.put("images", JSONArray(mediaList.map { it.data }))
            }
            if (isJson) body.put("format", "json")
            body.put("options", JSONObject().put("temperature", 0.2).put("num_predict", maxTokens))
            url = localBase(provider) + "/api/chat"
        } else {
            if (mediaList.isNotEmpty()) {
                val content = JSONArray()
                content.put(JSONObject().put("type", "text").put("text", prompt))
                for (m in mediaList) {
                    content.put(JSONObject().put("type", "image_url")
                        .put("image_url", JSONObject().put("url", "data:${m.mime};base64,${m.data}")))
                }
                user.put("content", content)
            } else user.put("content", prompt)
            if (isJson) body.put("response_format", JSONObject().put("type", "json_object"))
            body.put("temperature", 0.2).put("max_tokens", maxTokens)
            url = localBase(provider) + "/chat/completions"
        }
        body.put("messages", JSONArray()
            .put(JSONObject().put("role", "system").put("content", system)).put(user))
        val r = try {
            post(url, headers, body)
        } catch (e: AIError) {
            throw AIError("${providerName(provider)} inaccessible. Démarre son serveur local et vérifie l'adresse dans Paramètres.")
        }
        if (r.code >= 400) {
            val errText = r.body?.string() ?: ""; r.close()
            throw AIError(explainHttp(provider, r.code, errText) +
                (if (media != null) " Pour analyser une capture, charge un modèle avec vision." else ""))
        }
        val data = JSONObject(r.body!!.string()); r.close()
        return if (provider == "ollama") {
            (data.optJSONObject("message")?.optString("content") ?: "").trim()
        } else {
            (data.optJSONArray("choices")?.optJSONObject(0)
                ?.optJSONObject("message")?.optString("content") ?: "").trim()
        }
    }

    private fun callSingle(provider: String, key: String, model: String, system: String,
                           prompt: String, media: Any?, isJson: Boolean,
                           mime: String = "image/png", maxTokens: Int = 2048): String {
        return when {
            provider in SettingsStore.LOCAL_PROVIDERS ->
                callLocal(provider, key, model, system, prompt, media, isJson, mime, maxTokens)
            provider == "gemini" -> callGemini(key, model, system, prompt, media, isJson, maxTokens, mime)
            provider == "anthropic" -> callAnthropic(key, model, system, prompt, media, isJson, maxTokens, mime)
            provider in listOf("openai", "groq", "deepseek", "openrouter") ->
                callOpenAiStyle(provider, key, model, system, prompt, media, isJson, maxTokens, mime)
            else -> throw AIError("Fournisseur inconnu : $provider")
        }
    }

    data class ChatResult(val reply: String, val effectiveProvider: String)

    /**
     * Execute chat with automatic fallback across keys and providers.
     * Same contract as the Python chat_with_fallback.
     */
    fun chatWithFallback(
        provider: String, prompt: String,
        system: String = "You are a helpful assistant.",
        media: Any? = null, isJson: Boolean = false, mime: String = "image/png",
        onFallback: ((fromProvider: String, toProvider: String, reason: String, attempt: Int) -> Unit)? = null,
        isCancelled: () -> Boolean = { false },
        allowFallback: Boolean = true,
        maxTokens: Int = 2048,
    ): ChatResult {
        val primary = provider.ifEmpty { SettingsStore.str("provider", "gemini") }.lowercase()

        data class Candidate(val p: String, val k: String, val m: String)
        val candidates = mutableListOf<Candidate>()

        var pKeys = SettingsStore.getProviderKeys(primary)
        if (primary in SettingsStore.LOCAL_PROVIDERS && pKeys.isEmpty()) pKeys = listOf("")
        val pModel = SettingsStore.getModel(primary).trim()
        for (k in pKeys) candidates.add(Candidate(primary, k, pModel))

        for (other in SettingsStore.PROVIDERS) {
            if (!allowFallback || primary in SettingsStore.LOCAL_PROVIDERS ||
                other in SettingsStore.LOCAL_PROVIDERS || other == primary) continue
            for (k in SettingsStore.getProviderKeys(other)) {
                candidates.add(Candidate(other, k, SettingsStore.getModel(other).trim()))
            }
        }

        if (candidates.isEmpty()) {
            throw AIError("Aucune clé API configurée pour ${providerName(primary)} ni aucun autre fournisseur. " +
                "Renseigne tes clés dans Paramètres.")
        }

        val now = System.currentTimeMillis()
        candidates.sortBy { c ->
            val failTime = failedKeys[c.k] ?: 0L
            val fresh = (now - failTime) > FAILED_KEYS_COOLDOWN_MS
            (if (c.p == primary) 0 else 10) + (if (fresh) 0 else 100)
        }

        val errors = mutableListOf<String>()
        for ((i, c) in candidates.withIndex()) {
            if (isCancelled()) throw AIError("Requête annulée.")
            if (c.m.isEmpty()) {
                errors.add("${providerName(c.p)}: aucun modèle choisi dans Paramètres")
                continue
            }
            try {
                val res = callSingle(c.p, c.k, c.m, system, prompt, media, isJson, mime,
                    maxTokens.coerceIn(128, 4096))
                if (res.isBlank()) throw AIError("Le modèle a renvoyé une réponse vide. Essaie un autre modèle.")
                failedKeys.remove(c.k)
                return ChatResult(res, c.p)
            } catch (e: Exception) {
                if (isCancelled()) throw AIError("Requête annulée.")
                failedKeys[c.k] = System.currentTimeMillis()
                errors.add("${providerName(c.p)}: ${e.message}")
                if (i + 1 < candidates.size) {
                    val n = candidates[i + 1]
                    try { onFallback?.invoke(c.p, n.p, e.message ?: "", i + 1) } catch (_: Exception) {}
                }
            }
        }
        throw AIError("Tous les fournisseurs/clés ont échoué. Détails : ${errors.take(4).joinToString(" | ")}")
    }

    fun chat(provider: String, prompt: String, system: String = "You are a helpful assistant.",
             media: Any? = null, isJson: Boolean = false, mime: String = "image/png",
             maxTokens: Int = 2048): String =
        chatWithFallback(provider, prompt, system, media, isJson, mime,
            maxTokens = maxTokens).reply

    // ------------------------------------------------------- model lists
    fun listModels(provider: String): List<String> {
        val p = provider.lowercase()
        val key = SettingsStore.getApiKey(p)
        return try {
            when {
                p in SettingsStore.LOCAL_PROVIDERS -> listLocalModels(p)
                p == "gemini" -> {
                    if (key.isEmpty()) return emptyList()
                    val r = get("${ENDPOINTS.getValue("gemini")}?key=$key", emptyMap())
                    val out = mutableListOf<String>()
                    if (r.code < 400) {
                        val arr = JSONObject(r.body!!.string()).optJSONArray("models")
                        if (arr != null) for (i in 0 until arr.length()) {
                            arr.optJSONObject(i)?.optString("name")?.let { out.add(it.removePrefix("models/")) }
                        }
                    }
                    r.close(); out
                }
                p == "anthropic" -> {
                    if (key.isEmpty()) return emptyList()
                    listOf("claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5", "claude-3-5-sonnet-20241022")
                }
                else -> {
                    if (key.isEmpty()) return emptyList()
                    val url = ENDPOINTS.getValue(p).removeSuffix("/chat/completions") + "/models"
                    val r = get(url, mapOf("Authorization" to "Bearer $key"))
                    val out = mutableListOf<String>()
                    if (r.code < 400) {
                        val arr = JSONObject(r.body!!.string()).optJSONArray("data")
                        if (arr != null) for (i in 0 until arr.length()) {
                            arr.optJSONObject(i)?.optString("id")?.let { out.add(it) }
                        }
                    }
                    r.close(); out.sorted()
                }
            }
        } catch (_: Exception) { emptyList() }
    }

    private fun listLocalModels(provider: String): List<String> {
        val url = if (provider == "ollama") localBase(provider) + "/api/tags"
        else localBase(provider) + "/models"
        val r = get(url, emptyMap())
        if (r.code >= 400) { r.close(); return emptyList() }
        val data = JSONObject(r.body!!.string()); r.close()
        val out = mutableListOf<String>()
        if (provider == "ollama") {
            val arr = data.optJSONArray("models") ?: return emptyList()
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.optString("name")?.let { out.add(it) }
        } else {
            val arr = data.optJSONArray("data") ?: return emptyList()
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.optString("id")?.let { out.add(it) }
        }
        return out
    }
}

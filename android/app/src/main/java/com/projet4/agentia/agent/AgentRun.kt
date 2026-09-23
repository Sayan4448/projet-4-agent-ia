package com.projet4.agentia.agent

import android.content.Context
import com.projet4.agentia.ai.AiClient
import com.projet4.agentia.data.MemoryStore
import com.projet4.agentia.data.SettingsStore
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.math.roundToInt

/**
 * Port of agent.py's AgentRun — the observe→think→act loop.
 * Same JSON contract with the model; actions adapted to Android
 * (tap/swipe/type/back/home instead of mouse/keyboard/PowerShell).
 */
class AgentRun(
    private val context: Context,
    val goal: String,
    private val capture: ScreenCapture,
    private val emit: (event: String, data: Map<String, Any?>) -> Unit,
) {
    data class Step(val step: Int, val thought: String, val actions: String,
                    val done: Boolean, val summary: String, val message: String)

    private val cfg get() = SettingsStore.load()

    private val maxSteps = SettingsStore.int("max_steps", 20)
    private val grid = SettingsStore.bool("grid", true)
    private var imageWidth = SettingsStore.int("image_width", 1280)
    private var jpegQuality = SettingsStore.int("jpeg_quality", 80)
    private val stepDelay = SettingsStore.dbl("step_delay", 0.4)
    private val ecoMode = SettingsStore.bool("eco_mode", false)
    private val uiTreeEnabled = SettingsStore.bool("ui_tree_enabled", true)
    private val actionLimit =
        if (SettingsStore.bool("limit_actions_per_capture", true))
            SettingsStore.int("actions_per_capture", 3).coerceIn(1, 3)
        else 3
    private val provider = SettingsStore.str("provider", "gemini")
    var effectiveProvider = provider
        private set

    @Volatile private var stopFlag = false
    private val guidance = CopyOnWriteArrayList<String>()
    private val history = mutableListOf<String>()
    var currentStep = 0
        private set

    init {
        if (ecoMode) {
            imageWidth = minOf(if (imageWidth > 0) imageWidth else 960, 960)
            jpegQuality = minOf(if (jpegQuality > 0) jpegQuality else 60, 60)
        }
    }

    fun stop() { stopFlag = true }
    val stopped get() = stopFlag
    fun guide(text: String) { if (text.isNotBlank()) guidance.add(text.trim()) }

    private fun drainGuidance(): List<String> {
        val out = guidance.toList(); guidance.clear(); return out
    }

    // -------------------------------------------------------- actions
    private val ACTIONS_SIGNATURE = (
        "open_app(name='chrome'|'youtube'|'whatsapp'|'maps'|'settings'|... or package 'com.x.y'), " +
        "tap(x,y), double_tap(x,y), long_press(x,y), swipe(x1,y1,x2,y2), " +
        "scroll(direction='up|down|left|right'), type_text(text), press_enter(), " +
        "press_back(), press_home(), press_recents(), open_notifications(), " +
        "open_url(url='https://...'), search_web(query='...'), wait(seconds<=5)"
    )

    private fun toReal(args: JSONObject, frameW: Int, frameH: Int,
                       realW: Int, realH: Int): Pair<Float, Float>? {
        if (!args.has("x") || !args.has("y")) return null
        val nx = args.optDouble("x", Double.NaN)
        val ny = args.optDouble("y", Double.NaN)
        if (nx.isNaN() || ny.isNaN()) return null
        if (nx < -50 || nx > 1050 || ny < -50 || ny > 1050) return null
        val cx = nx.coerceIn(0.0, 1000.0); val cy = ny.coerceIn(0.0, 1000.0)
        // normalized 0-1000 → real device px (frame may be downscaled)
        return Pair((cx / 1000.0 * realW).roundToInt().toFloat(),
                    (cy / 1000.0 * realH).roundToInt().toFloat())
    }

    private fun execute(name: String, args: JSONObject,
                        frameW: Int, frameH: Int, realW: Int, realH: Int): String {
        val a11y = AgentAccessibilityService.instance
        fun needA11y() = a11y ?: throw IllegalStateException(
            "service d'accessibilité non activé")
        fun pt(): Pair<Float, Float> = toReal(args, frameW, frameH, realW, realH)
            ?: throw IllegalArgumentException("coordonnées x,y manquantes ou hors 0-1000")

        return when (name) {
            "open_app" -> {
                val r = AppLauncher.launch(context, args.optString("name"))
                if (r.ok) "ok: ${r.detail}" else "erreur: ${r.detail}"
            }
            "tap" -> {
                val (x, y) = pt()
                val ok = needA11y().tap(x, y)
                if (!ok) needA11y().clickNodeAt((x / realW * 1000), (y / realH * 1000))
                "tap($x,$y) → $ok"
            }
            "double_tap" -> {
                val (x, y) = pt()
                "double_tap → ${needA11y().doubleTap(x, y)}"
            }
            "long_press" -> {
                val (x, y) = pt()
                "long_press → ${needA11y().longPress(x, y)}"
            }
            "swipe" -> {
                val p1 = toReal(args, frameW, frameH, realW, realH)
                    ?: throw IllegalArgumentException("x1,y1 manquants")
                val x2 = args.optDouble("x2", Double.NaN)
                val y2 = args.optDouble("y2", Double.NaN)
                if (x2.isNaN() || y2.isNaN()) throw IllegalArgumentException("x2,y2 manquants")
                val rx2 = (x2.coerceIn(0.0, 1000.0) / 1000.0 * realW).toFloat()
                val ry2 = (y2.coerceIn(0.0, 1000.0) / 1000.0 * realH).toFloat()
                "swipe → ${needA11y().swipe(p1.first, p1.second, rx2, ry2)}"
            }
            "scroll" -> {
                val dir = args.optString("direction", "up")
                val hasPt = args.has("x") && args.has("y")
                val ok = if (hasPt) {
                    val (x, y) = pt()
                    needA11y().scrollAt(x, y, dir)
                } else needA11y().scroll(dir)
                "scroll $dir → $ok"
            }
            "type_text" -> {
                val text = args.optString("text", "")
                val ok = needA11y().typeText(text)
                val preview = text.take(80)
                "écrit «$preview» → $ok"
            }
            "press_enter" -> "enter → ${needA11y().pressEnter()}"
            "press_back" -> "back → ${needA11y().global("back")}"
            "press_home" -> "home → ${needA11y().global("home")}"
            "press_recents" -> "recents → ${needA11y().global("recents")}"
            "open_notifications" -> "notifs → ${needA11y().global("notifications")}"
            "open_url" -> {
                val r = AppLauncher.openUrl(context, args.optString("url"))
                if (r.ok) "ok: ${r.detail}" else "erreur: ${r.detail}"
            }
            "search_web" -> {
                val r = AppLauncher.searchWeb(context, args.optString("query"))
                if (r.ok) "ok: ${r.detail}" else "erreur: ${r.detail}"
            }
            "wait" -> {
                val s = args.optDouble("seconds", 1.0).coerceIn(0.0, 5.0)
                Thread.sleep((s * 1000).toLong()); "waited ${s}s"
            }
            else -> "action inconnue: $name"
        }
    }

    // -------------------------------------------------------- prompt
    private val SYSTEM_PROMPT = """
You are Agent Screen, an expert Android-automation agent running on the user's phone.
You see a screenshot with a labeled coordinate grid (NORMALIZED 0-1000 coordinates:
0=left/top edge, 1000=right/bottom) and — when available — a text dump of the UI
element tree with element bounds in the same 0-1000 coordinates and flags
(click/edit/scroll). Act through precise, verifiable actions. Never guess what
you can check.

== GROUND RULES ==
- To open an app use open_app(name=...) — NEVER tap icons on the home screen:
  icon positions vary and misidentification launches the wrong app.
- Prefer the UI tree when it is given: if the target element is listed, aim at
  the CENTER of its bounds rectangle — far more reliable than guessing.
- To fill a text field: tap its bounds center first, then type_text on the next
  step once the field is focused (then press_enter to submit if needed).
- scroll(direction='up') scrolls the content upward = reveals content BELOW.
  Prefer giving scroll x,y coords aimed at the list/element when it is not
  fullscreen — a node's native scroll beats a blind swipe.
- If an action reports failure or the screenshot shows no change, change
  strategy: re-aim at the element center, scroll to reveal it, or use the UI
  tree's exact bounds. Never repeat the identical failing action.
- Popup / consent / login walls: dismiss them first (back, tap the close/accept
  button), then continue.
- Verify on the next screenshot that what you did really happened.
- NEVER set done=true unless a previous step really executed an action that
  achieved the goal. Claiming success without acting is forbidden.
- The user sees your 'message' field live — keep it short, in French.
"""

    private fun extractJson(text: String): JSONObject? {
        var t = text.trim()
        val fence = Regex("```(?:json)?\\s*(\\{.*?\\})\\s*```", RegexOption.DOT_MATCHES_ALL).find(t)
        if (fence != null) t = fence.groupValues[1]
        return try { JSONObject(t) } catch (_: Exception) {
            val m = Regex("\\{.*\\}", RegexOption.DOT_MATCHES_ALL).find(t)
            try { if (m != null) JSONObject(m.value) else null } catch (_: Exception) { null }
        }
    }

    private fun parseActions(obj: JSONObject): List<Pair<String, JSONObject>> {
        val out = mutableListOf<Pair<String, JSONObject>>()
        val arr = obj.optJSONArray("actions")
        if (arr != null) {
            for (i in 0 until minOf(arr.length(), actionLimit)) {
                val a = arr.optJSONObject(i) ?: continue
                out.add(a.optString("name") to (a.optJSONObject("args") ?: JSONObject()))
            }
        } else {
            obj.optJSONObject("action")?.let {
                out.add(it.optString("name") to (it.optJSONObject("args") ?: JSONObject()))
            }
        }
        return out.take(actionLimit)
    }

    private fun historyText(): String {
        if (history.isEmpty()) return ""
        val recent = history.takeLast(if (ecoMode) 2 else 4)
        return " Recent steps (oldest first): " + recent.joinToString(" || ") + "."
    }

    private fun appsText(): String {
        val pkgs = AppLauncher.installedApps(context, 40)
        if (pkgs.isEmpty()) return ""
        return " Installed apps: " + pkgs.joinToString("; ") + "."
    }

    // -------------------------------------------------------- the loop
    fun run(): Map<String, Any?> {
        var outcome = "max_steps"
        var finalSummary = ""
        var actedSoFar = false
        var emptyReplies = 0

        emit("status", mapOf("key" to "first_shot"))
        // A fresh VirtualDisplay needs a few hundred ms before its first frame.
        var frame = capture.capture(imageWidth, jpegQuality, grid)
        var tries = 0
        while (frame == null && tries < 10 && !stopped) {
            Thread.sleep(250); tries++
            frame = capture.capture(imageWidth, jpegQuality, grid)
        }
        if (frame == null) {
            emit("error", mapOf("message" to "capture d'écran indisponible"))
            return mapOf("outcome" to "error", "summary" to "capture indisponible")
        }
        var f = frame!!   // non-null from here on
        emit("screenshot", mapOf("b64" to f.base64, "mime" to f.mime))

        val contextText = ("Goal: $goal. All x/y action coordinates MUST be NORMALIZED " +
            "integers from 0 to 1000 (0=left/top edge, 1000=right/bottom edge), as labeled " +
            "on the grid. The app converts them to physical pixels — never apply scaling " +
            "or offsets yourself.")

        val chainRule = (
            " Reply ONLY with JSON: {\"thought\": \"...\", \"actions\": [{\"name\": \"...\", " +
            "\"args\": {...}}], \"done\": false, \"summary\": \"\", \"message\": \"optional short " +
            "reply to user in French\"} — up to $actionLimit action(s) per screenshot. " +
            "NEVER set done=true unless your previous actions really achieved the goal."
        )

        var system = SYSTEM_PROMPT
        try {
            for (i in 1..maxSteps) {
                if (stopped) { outcome = "stopped"; break }
                currentStep = i

                val notes = drainGuidance()
                val extra = if (notes.isNotEmpty()) {
                    notes.forEach { emit("guidance", mapOf("text" to it)) }
                    " User guidance (follow it now): " + notes.joinToString(" | ")
                } else ""

                emit("thinking", mapOf("step" to i))
                val remembered = if (SettingsStore.bool("memory_enabled", true))
                    MemoryStore.promptBlock(this.context) else ""

                // fresh UI tree (Android advantage)
                val treeText = if (uiTreeEnabled) {
                    val t = AgentAccessibilityService.instance?.dumpUiTree() ?: ""
                    if (t.isNotEmpty()) "\n\nUI tree (bounds in 0-1000 coords, flags: click/edit/scroll):\n$t" else ""
                } else ""

                val pkg = AgentAccessibilityService.instance?.currentAppPackage() ?: ""
                val pkgText = if (pkg.isNotEmpty()) " Foreground app: $pkg." else ""

                val reply: AiClient.ChatResult
                try {
                    reply = AiClient.chatWithFallback(
                        provider,
                        prompt = "$contextText$remembered$pkgText$treeText${historyText()}$extra\n\n" +
                            "Available actions: $ACTIONS_SIGNATURE\n$chainRule",
                        system = system,
                        media = f.base64, isJson = true, mime = f.mime,
                        isCancelled = { stopped },
                        maxTokens = if (ecoMode) 900 else 1600,
                        onFallback = { from, to, reason, _ ->
                            effectiveProvider = to
                            emit("fallback", mapOf("from" to from, "to" to to, "reason" to reason))
                        },
                    )
                } catch (e: AiClient.AIError) {
                    if (stopped) { outcome = "stopped"; break }
                    emit("error", mapOf("message" to e.message))
                    emptyReplies++
                    if (emptyReplies >= 3) { outcome = "error"; break }
                    continue
                }
                emptyReplies = 0

                val obj = extractJson(reply.reply)
                if (obj == null) {
                    emit("status", mapOf("key" to "unparsed_reply"))
                    history.add("step $i: réponse IA non-JSON")
                    continue
                }
                val thought = obj.optString("thought", "")
                val summary = obj.optString("summary", "")
                val message = obj.optString("message", "")
                if (message.isNotEmpty()) emit("agent_message", mapOf("text" to message))
                val actions = parseActions(obj)

                emit("step", mapOf(
                    "step" to i, "thought" to thought, "summary" to summary,
                    "actions" to actions.map { it.first }.joinToString(", ")
                ))

                // execute actions
                for ((name, args) in actions) {
                    if (stopped) { outcome = "stopped"; break }
                    val resultText = try {
                        emit("action", mapOf("name" to name, "args" to args.toString()))
                        // flash the tap indicator overlay if granted
                        if (name in listOf("tap", "double_tap", "long_press")) {
                            toReal(args, f.width, f.height, f.realW, f.realH)
                                ?.let { (x, y) -> emit("cursor", mapOf("x" to x, "y" to y)) }
                        }
                        execute(name, args, f.width, f.height, f.realW, f.realH)
                    } catch (e: Exception) {
                        "erreur: ${e.message}"
                    }
                    emit("action_result", mapOf("name" to name, "result" to resultText))
                    history.add("step $i: $name → ${resultText.take(120)}")
                    actedSoFar = true
                }

                if (obj.optBoolean("done", false)) {
                    if (!actedSoFar) {
                        // anti-hallucination, same rule as desktop
                        history.add("step $i: done refusé (aucune action exécutée)")
                        emit("status", mapOf("key" to "done_rejected"))
                        continue
                    }
                    finalSummary = summary.ifEmpty { message }
                    outcome = "done"
                    break
                }

                // next observation
                Thread.sleep((stepDelay * 1000).toLong().coerceAtLeast(100))
                val newFrame = capture.capture(imageWidth, jpegQuality, grid)
                if (newFrame != null) {
                    f = newFrame
                    emit("screenshot", mapOf("b64" to f.base64, "mime" to f.mime))
                }
            }
        } finally {
            emit("finished", mapOf("outcome" to outcome, "summary" to finalSummary))
        }
        return mapOf("outcome" to outcome, "summary" to finalSummary,
                     "steps" to currentStep, "provider" to effectiveProvider)
    }
}

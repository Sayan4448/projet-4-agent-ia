package com.projet4.agentia.ui.screens

import android.content.Intent
import android.graphics.BitmapFactory
import android.provider.Settings
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.projet4.agentia.agent.AgentAccessibilityService
import com.projet4.agentia.agent.AgentService
import com.projet4.agentia.ui.accentColor
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

data class LogLine(val icon: String, val text: String)

@Composable
fun AgentScreen(onStartRun: (String) -> Unit) {
    val context = LocalContext.current
    val running by AgentService.running.collectAsState()

    var goal by remember { mutableStateOf("") }
    var guideText by remember { mutableStateOf("") }
    val log = remember { mutableStateListOf<LogLine>() }
    var lastShot by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var currentAction by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(Unit) {
        AgentService.events.collect { (event, data) ->
            when (event) {
                "step" -> {
                    log.add(LogLine("●", "Étape ${data["step"]} — ${data["thought"]}"))
                    val acts = data["actions"]?.toString().orEmpty()
                    if (acts.isNotEmpty()) log.add(LogLine("▸", acts))
                }
                "action" -> currentAction = data["name"]?.toString() ?: ""
                "action_result" -> {
                    log.add(LogLine("→", data["result"]?.toString() ?: ""))
                    currentAction = ""
                }
                "agent_message" -> log.add(LogLine("✦", data["text"]?.toString() ?: ""))
                "fallback" -> log.add(LogLine("⇄",
                    "Bascule ${data["from"]} → ${data["to"]} (${data["reason"]})"))
                "guidance" -> log.add(LogLine("◈", "Ta consigne: ${data["text"]}"))
                "error" -> log.add(LogLine("✗", data["message"]?.toString() ?: "erreur"))
                "screenshot" -> {
                    val b64 = data["b64"]?.toString()
                    if (b64 != null) {
                        try {
                            val bytes = Base64.decode(b64, Base64.DEFAULT)
                            lastShot = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        } catch (_: Exception) {}
                    }
                }
                "finished" -> {
                    val outcome = data["outcome"]?.toString()
                    val summary = data["summary"]?.toString()
                    log.add(LogLine("■",
                        "Terminé ($outcome)${if (!summary.isNullOrEmpty()) " — $summary" else ""}"))
                }
            }
            if (log.isNotEmpty()) listState.animateScrollToItem(log.size - 1)
        }
    }

    val a11yOn = remember { mutableStateOf(AgentAccessibilityService.isEnabled()) }
    LaunchedEffect(Unit) {
        while (isActive) {
            a11yOn.value = AgentAccessibilityService.isEnabled()
            delay(1500)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("✦ Projet 4, agent IA", style = MaterialTheme.typography.headlineSmall)
        Text("Votre objectif. Son prochain mouvement.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        if (!a11yOn.value) {
            Card(colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.errorContainer)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Service d'accessibilité requis",
                        style = MaterialTheme.typography.titleSmall)
                    Text("L'agent a besoin du service d'accessibilité pour toucher l'écran à ta " +
                        "place. Active « Projet 4, agent IA » dans les paramètres Android.",
                        style = MaterialTheme.typography.bodySmall)
                    Button(onClick = {
                        context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }) { Text("Ouvrir les paramètres") }
                }
            }
        }

        OutlinedTextField(
            value = goal,
            onValueChange = { goal = it },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("Décris ton objectif… ex: « Ouvre YouTube et cherche des chats »") },
            enabled = !running,
            maxLines = 3,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { onStartRun(goal.trim()) },
                enabled = !running && goal.isNotBlank() && a11yOn.value,
            ) { Text("Lancer l'agent") }
            if (running) {
                OutlinedButton(
                    onClick = {
                        context.startService(Intent(context, AgentService::class.java)
                            .setAction(AgentService.ACTION_STOP))
                    },
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.error),
                ) { Text("Arrêter") }
            }
            if (!Settings.canDrawOverlays(context)) {
                TextButton(onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            android.net.Uri.parse("package:${context.packageName}"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }) { Text("Curseur visuel") }
            }
        }

        if (running && currentAction.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).clip(RoundedCornerShape(50))
                    .background(accentColor()))
                Spacer(Modifier.size(8.dp))
                Text("en cours: $currentAction", style = MaterialTheme.typography.bodySmall)
            }
        }

        if (running) {
            OutlinedTextField(
                value = guideText,
                onValueChange = { guideText = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Guide l'agent en direct…") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    AgentService.activeService?.guide(guideText)
                    guideText = ""
                }),
            )
        }

        lastShot?.let { bmp ->
            Image(
                bitmap = bmp.asImageBitmap(),
                contentDescription = "dernière capture",
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .clip(RoundedCornerShape(12.dp)),
                contentScale = ContentScale.Crop,
            )
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            items(log) { line ->
                Row {
                    Text(line.icon, color = accentColor(),
                        modifier = Modifier.widthIn(min = 20.dp))
                    Text(line.text, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

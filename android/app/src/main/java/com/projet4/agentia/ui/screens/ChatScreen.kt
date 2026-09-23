package com.projet4.agentia.ui.screens

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.projet4.agentia.ai.AiClient
import com.projet4.agentia.data.ConversationStore
import com.projet4.agentia.data.SettingsStore
import com.projet4.agentia.ui.accentColor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

@Composable
fun ChatScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()

    var conv by remember {
        mutableStateOf(ConversationStore.loadAll().firstOrNull()
            ?: ConversationStore.Conversation())
    }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var attached by remember { mutableStateOf<Bitmap?>(null) }
    var showConvList by remember { mutableStateOf(false) }
    var allConvs by remember { mutableStateOf(ConversationStore.loadAll()) }

    val pickImage = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let {
            try {
                context.contentResolver.openInputStream(it)?.use { stream ->
                    var bmp = BitmapFactory.decodeStream(stream)
                    if (bmp != null && bmp.width > 1280) {
                        bmp = Bitmap.createScaledBitmap(
                            bmp, 1280, bmp.height * 1280 / bmp.width, true)
                    }
                    attached = bmp
                }
            } catch (_: Exception) {}
        }
    }

    fun send() {
        val text = input.trim()
        if (text.isEmpty() || sending) return
        sending = true
        input = ""
        val img = attached; attached = null
        conv.messages.add(ConversationStore.Message("user", text))
        if (conv.title == "Nouvelle discussion") conv.title = ConversationStore.titleFrom(text)
        ConversationStore.save(conv)
        conv = conv.copy()   // new reference → recompose

        scope.launch(Dispatchers.IO) {
            val reply = try {
                val eco = SettingsStore.bool("chat_eco", true)
                val maxTok = if (eco) SettingsStore.int("chat_response_tokens", 700) else 2048
                val media: Any? = img?.let {
                    val baos = ByteArrayOutputStream()
                    it.compress(Bitmap.CompressFormat.JPEG, 80, baos)
                    Base64.encodeToString(baos.toByteArray(), Base64.NO_WRAP)
                }
                val history = conv.messages.takeLast(
                    if (eco) SettingsStore.int("chat_context_messages", 6) else 10)
                val prompt = buildString {
                    for (m in history.dropLast(1)) {
                        append(if (m.role == "user") "User: " else "Assistant: ")
                        append(m.text).append("\n")
                    }
                    append("User: ").append(text)
                }
                val res = AiClient.chatWithFallback(
                    SettingsStore.str("provider", "gemini"), prompt,
                    system = "Tu es un assistant utile qui répond en français, de façon concise.",
                    media = media, mime = "image/jpeg", maxTokens = maxTok)
                res
            } catch (e: AiClient.AIError) {
                null to e.message
            } catch (e: Exception) {
                null to (e.message ?: "erreur inconnue")
            }
            withContext(Dispatchers.Main) {
                when (reply) {
                    is AiClient.ChatResult -> conv.messages.add(
                        ConversationStore.Message("assistant", reply.reply, reply.effectiveProvider))
                    else -> conv.messages.add(
                        ConversationStore.Message("assistant",
                            "Erreur: ${(reply as? Pair<*, *>)?.second ?: "inconnue"}"))
                }
                ConversationStore.save(conv)
                conv = conv.copy()
                sending = false
            }
        }
    }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(conv.title, style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f), maxLines = 1)
            TextButton(onClick = {
                conv = ConversationStore.Conversation()
            }) { Text("+") }
            TextButton(onClick = {
                allConvs = ConversationStore.loadAll()
                showConvList = true
            }) { Text("🗂") }
        }

        DropdownMenu(expanded = showConvList, onDismissRequest = { showConvList = false }) {
            allConvs.take(30).forEach { c ->
                DropdownMenuItem(
                    text = { Text((if (c.favorite) "★ " else "") + c.title, maxLines = 1) },
                    onClick = {
                        conv = c
                        showConvList = false
                    })
            }
        }

        LazyColumn(state = listState, modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            items(conv.messages) { m ->
                val isUser = m.role == "user"
                Row(horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
                    modifier = Modifier.fillMaxWidth()) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (isUser) accentColor()
                                else MaterialTheme.colorScheme.surfaceVariant),
                        shape = RoundedCornerShape(
                            topStart = 16.dp, topEnd = 16.dp,
                            bottomStart = if (isUser) 16.dp else 4.dp,
                            bottomEnd = if (isUser) 4.dp else 16.dp),
                        modifier = Modifier.widthIn(max = 300.dp),
                    ) {
                        Column(Modifier.padding(10.dp)) {
                            Text(m.text, style = MaterialTheme.typography.bodyMedium,
                                color = if (isUser) MaterialTheme.colorScheme.onPrimary
                                    else MaterialTheme.colorScheme.onSurfaceVariant)
                            if (!isUser && m.provider.isNotEmpty()) {
                                Text(m.provider, style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
            if (sending) {
                item { Text("…", style = MaterialTheme.typography.bodyMedium) }
            }
        }

        attached?.let {
            Image(bitmap = it.asImageBitmap(), contentDescription = "image jointe",
                modifier = Modifier.heightIn(max = 120.dp).clip(RoundedCornerShape(8.dp)),
                contentScale = ContentScale.Fit)
        }

        Row(verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedButton(onClick = { pickImage.launch("image/*") }) { Text("📎") }
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Message…") },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { send() }),
            )
            Button(onClick = { send() }, enabled = !sending) { Text("Envoyer") }
        }
    }
}

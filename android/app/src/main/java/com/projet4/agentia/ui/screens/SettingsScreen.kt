package com.projet4.agentia.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.projet4.agentia.ai.AiClient
import com.projet4.agentia.data.MemoryStore
import com.projet4.agentia.data.SettingsStore
import com.projet4.agentia.ui.ACCENT_COLORS
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val scope = rememberCoroutineScope()
    var version by remember { mutableStateOf(0) }   // re-read trigger
    @Suppress("UNUSED_VARIABLE") val v = version
    val cfg = SettingsStore.load()

    fun <T> get(key: String): T? = @Suppress("UNCHECKED_CAST") (cfg[key] as? T)

    var provider by remember { mutableStateOf(SettingsStore.str("provider", "gemini")) }
    var testingConn by remember { mutableStateOf<String?>(null) }
    var connResult by remember { mutableStateOf<String?>(null) }
    var availableModels by remember { mutableStateOf<List<String>>(emptyList()) }
    var loadingModels by remember { mutableStateOf(false) }

    @Suppress("UNCHECKED_CAST")
    val apiKeys = cfg["api_keys"] as? Map<String, String> ?: emptyMap()
    @Suppress("UNCHECKED_CAST")
    val models = cfg["models"] as? Map<String, String> ?: emptyMap()

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Paramètres", style = MaterialTheme.typography.titleLarge)

        // ---------- provider picker
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Fournisseur IA", style = MaterialTheme.typography.titleSmall)
                var expanded by remember { mutableStateOf(false) }
                ExposedDropdownMenuBox(expanded = expanded,
                    onExpandedChange = { expanded = it }) {
                    OutlinedTextField(
                        value = SettingsStore.PROVIDER_NAMES[provider] ?: provider,
                        onValueChange = {},
                        readOnly = true,
                        modifier = Modifier.fillMaxWidth().menuAnchor(),
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                    )
                    ExposedDropdownMenu(expanded = expanded,
                        onDismissRequest = { expanded = false }) {
                        SettingsStore.PROVIDERS.forEach { p ->
                            DropdownMenuItem(
                                text = { Text(SettingsStore.PROVIDER_NAMES[p] ?: p) },
                                onClick = {
                                    provider = p
                                    SettingsStore.save(mapOf("provider" to p))
                                    expanded = false
                                    version++
                                })
                        }
                    }
                }
            }
        }

        // ---------- API key / local URL
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val isLocal = provider in SettingsStore.LOCAL_PROVIDERS
                Text(if (isLocal) "Serveur local" else "Clé API",
                    style = MaterialTheme.typography.titleSmall)
                if (isLocal) {
                    var url by remember(provider) {
                        mutableStateOf(SettingsStore.getLocalUrl(provider))
                    }
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("http://192.168.1.x:11434") },
                        singleLine = true,
                    )
                    TextButton(onClick = {
                        SettingsStore.save(mapOf("local_urls" to mapOf(provider to url)))
                        version++
                    }) { Text("Enregistrer l'adresse") }
                    Text("Sur le téléphone, « 127.0.0.1 » désigne le téléphone lui-même — " +
                        "mets l'adresse IP de ta machine (ex: http://192.168.1.10:11434).",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    var key by remember(provider) {
                        mutableStateOf(apiKeys[provider] ?: "")
                    }
                    OutlinedTextField(
                        value = key,
                        onValueChange = { key = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("sk-…  (plusieurs clés séparées par des virgules)") },
                        singleLine = true,
                    )
                    TextButton(onClick = {
                        SettingsStore.save(mapOf("api_keys" to mapOf(provider to key)))
                        version++
                    }) { Text("Enregistrer la clé") }
                }
            }
        }

        // ---------- model picker
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Modèle", style = MaterialTheme.typography.titleSmall)
                var model by remember(provider) {
                    mutableStateOf(models[provider] ?: "")
                }
                OutlinedTextField(
                    value = model,
                    onValueChange = { model = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = {
                        SettingsStore.save(mapOf("models" to mapOf(provider to model)))
                        version++
                    }) { Text("Enregistrer") }
                    TextButton(onClick = {
                        loadingModels = true
                        scope.launch(Dispatchers.IO) {
                            val list = AiClient.listModels(provider)
                            withContext(Dispatchers.Main) {
                                availableModels = list
                                loadingModels = false
                            }
                        }
                    }) { Text(if (loadingModels) "Chargement…" else "Charger la liste") }
                }
                if (availableModels.isNotEmpty()) {
                    Text("Modèles disponibles — touche pour choisir:",
                        style = MaterialTheme.typography.bodySmall)
                    Column(Modifier.height(200.dp).verticalScroll(rememberScrollState())) {
                        availableModels.take(80).forEach { m ->
                            TextButton(onClick = {
                                model = m
                                SettingsStore.save(mapOf("models" to mapOf(provider to m)))
                                version++
                            }) { Text(m, style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
            }
        }

        // ---------- test connexion
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Connexion", style = MaterialTheme.typography.titleSmall)
                Button(onClick = {
                    testingConn = provider
                    connResult = null
                    scope.launch(Dispatchers.IO) {
                        val r = try {
                            AiClient.chat(provider, "Réponds seulement: ok",
                                system = "You are a test probe.", maxTokens = 16)
                            "Connexion réussie ✓ — $provider répond."
                        } catch (e: Exception) {
                            e.message ?: "échec inconnu"
                        }
                        withContext(Dispatchers.Main) {
                            connResult = r; testingConn = null
                        }
                    }
                }, enabled = testingConn == null) {
                    Text(if (testingConn != null) "Test en cours…" else "Tester la connexion")
                }
                connResult?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
        }

        // ---------- run options
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Agent", style = MaterialTheme.typography.titleSmall)

                Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()) {
                    Text("Mode éco (images 960px, JPEG 60)", Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall)
                    Switch(
                        checked = SettingsStore.bool("eco_mode"),
                        onCheckedChange = {
                            SettingsStore.save(mapOf("eco_mode" to it)); version++
                        })
                }
                Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()) {
                    Text("Grille de coordonnées sur les captures", Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall)
                    Switch(
                        checked = SettingsStore.bool("grid", true),
                        onCheckedChange = {
                            SettingsStore.save(mapOf("grid" to it)); version++
                        })
                }
                Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()) {
                    Text("Arbre UI envoyé au modèle (Android)", Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall)
                    Switch(
                        checked = SettingsStore.bool("ui_tree_enabled", true),
                        onCheckedChange = {
                            SettingsStore.save(mapOf("ui_tree_enabled" to it)); version++
                        })
                }

                Text("Étapes max: ${SettingsStore.int("max_steps", 20)}",
                    style = MaterialTheme.typography.bodySmall)
                Slider(
                    value = SettingsStore.int("max_steps", 20).toFloat(),
                    onValueChange = {
                        SettingsStore.save(mapOf("max_steps" to it.toInt())); version++
                    },
                    valueRange = 5f..40f, steps = 34,
                )
            }
        }

        // ---------- accent
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Couleur d'accent", style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    ACCENT_COLORS.keys.forEach { a ->
                        FilterChip(
                            selected = SettingsStore.str("accent", "violet") == a,
                            onClick = {
                                SettingsStore.save(mapOf("accent" to a)); version++
                            },
                            label = { Text(a) })
                    }
                }
            }
        }

        // ---------- memory
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Mémoire", style = MaterialTheme.typography.titleSmall)
                Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()) {
                    Text("L'agent retient tes préférences", Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall)
                    Switch(
                        checked = SettingsStore.bool("memory_enabled", true),
                        onCheckedChange = {
                            SettingsStore.save(mapOf("memory_enabled" to it)); version++
                        })
                }
                val mem = MemoryStore.list()
                if (mem.isEmpty()) {
                    Text("Aucune préférence mémorisée.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                mem.forEachIndexed { i, item ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("• $item", Modifier.weight(1f),
                            style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = { MemoryStore.removeAt(i); version++ }) {
                            Text("✕")
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        Text("Projet 4, agent IA — Android · port du client Windows",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

package com.projet4.agentia.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.projet4.agentia.data.RunHistoryStore
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HistoryScreen() {
    var runs by remember { mutableStateOf(RunHistoryStore.loadAll()) }
    var expanded by remember { mutableStateOf<String?>(null) }
    val fmt = remember { SimpleDateFormat("dd MMM HH:mm", Locale.FRENCH) }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Historique des missions", style = MaterialTheme.typography.titleLarge)

        if (runs.isEmpty()) {
            Text("Aucune mission enregistrée pour l'instant.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(runs) { run ->
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    onClick = { expanded = if (expanded == run.id) null else run.id },
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(run.goal, style = MaterialTheme.typography.titleSmall,
                                    maxLines = 2)
                                Text(
                                    "${fmt.format(Date(run.startedAt))} · ${run.outcome}" +
                                        (if (run.provider.isNotEmpty()) " · ${run.provider}" else ""),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Text(if (expanded == run.id) "▾" else "▸")
                        }
                        if (run.summary.isNotEmpty()) {
                            Spacer(Modifier.height(4.dp))
                            Text(run.summary, style = MaterialTheme.typography.bodySmall)
                        }
                        if (expanded == run.id && run.log.isNotEmpty()) {
                            Spacer(Modifier.height(8.dp))
                            run.log.takeLast(40).forEach { line ->
                                Text(line, style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
    }
}

package com.projet4.agentia

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.projet4.agentia.agent.AgentService
import com.projet4.agentia.agent.ScreenCapture
import com.projet4.agentia.ui.AgentTheme
import com.projet4.agentia.ui.screens.AgentScreen
import com.projet4.agentia.ui.screens.ChatScreen
import com.projet4.agentia.ui.screens.HistoryScreen
import com.projet4.agentia.ui.screens.SettingsScreen
import androidx.compose.ui.Modifier

class MainActivity : ComponentActivity() {

    /** Goal waiting for the projection consent to come back. */
    private var pendingGoal by mutableStateOf<String?>(null)

    private val projectionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { res ->
        val goal = pendingGoal
        pendingGoal = null
        if (res.resultCode == RESULT_OK && res.data != null && goal != null) {
            startAgentService(goal, res.resultCode, res.data!!)
        }
    }

    private val notifLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED) {
            notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            AgentTheme {
                val nav = rememberNavController()
                val backStack by nav.currentBackStackEntryAsState()
                val current = backStack?.destination?.route ?: "agent"
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            NavigationBarItem(
                                selected = current == "agent",
                                onClick = { nav.navigate("agent") { popUpTo("agent"); launchSingleTop = true } },
                                icon = { Icon(Icons.Filled.SmartToy, "Agent") },
                                label = { Text("Agent") })
                            NavigationBarItem(
                                selected = current == "chat",
                                onClick = { nav.navigate("chat") { launchSingleTop = true } },
                                icon = { Icon(Icons.Filled.PlayArrow, "Chat") },
                                label = { Text("Chat") })
                            NavigationBarItem(
                                selected = current == "history",
                                onClick = { nav.navigate("history") { launchSingleTop = true } },
                                icon = { Icon(Icons.Filled.History, "Historique") },
                                label = { Text("Historique") })
                            NavigationBarItem(
                                selected = current == "settings",
                                onClick = { nav.navigate("settings") { launchSingleTop = true } },
                                icon = { Icon(Icons.Filled.Settings, "Paramètres") },
                                label = { Text("Paramètres") })
                        }
                    }
                ) { padding ->
                    NavHost(nav, startDestination = "agent",
                            modifier = Modifier.padding(padding)) {
                        composable("agent") {
                            AgentScreen(
                                onStartRun = { goal -> beginRun(goal) },
                            )
                        }
                        composable("chat") { ChatScreen() }
                        composable("history") { HistoryScreen() }
                        composable("settings") { SettingsScreen() }
                    }
                }
            }
        }
    }

    private fun beginRun(goal: String) {
        pendingGoal = goal
        projectionLauncher.launch(ScreenCapture.consentIntent(this))
    }

    private fun startAgentService(goal: String, resultCode: Int, data: Intent) {
        val i = Intent(this, AgentService::class.java).apply {
            putExtra(AgentService.EXTRA_GOAL, goal)
            putExtra(AgentService.EXTRA_RESULT_CODE, resultCode)
            putExtra(AgentService.EXTRA_RESULT_DATA, data)
        }
        startForegroundService(i)
    }
}

package com.projet4.agentia

import android.app.Application
import com.projet4.agentia.data.ConversationStore
import com.projet4.agentia.data.MemoryStore
import com.projet4.agentia.data.RunHistoryStore
import com.projet4.agentia.data.SettingsStore

class AgentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        SettingsStore.init(this)
        ConversationStore.init(this)
        MemoryStore.init(this)
        RunHistoryStore.init(this)
    }
}

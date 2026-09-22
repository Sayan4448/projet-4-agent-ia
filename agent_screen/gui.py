"""Agent Screen — native Windows desktop UI (Tkinter), modern dark theme, FR/EN.

Two modes:
  🤖 Agent — controls mouse/keyboard; live activity panel on the right shows
             thoughts, executed commands, fallback events, and screenshots after each step.
  💬 Chat  — plain conversation, optionally with a fast compressed screenshot attached.

Game mode (🎮): raw scan-code keys, held mouse buttons and relative mouse
movement for DirectInput games (Counter-Strike…). Needs admin rights so
games accept the simulated input.
"""
import base64
import io
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from . import __version__, agent, display, input_control, server
from .agent import AgentRun
from .ai_client import AIError, chat, chat_with_fallback, list_models
from .paths import app_root, load_dotenv_if_present
from .settings import (PROVIDERS, get_api_key, get_provider_keys, get_available_providers, load,
                       migrate_legacy_keys, save, LOCAL_PROVIDERS)
from .overlay import AgentOverlay
from . import conversations

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
}

# ----------------------------------------------------------------- strings
S = {
    "app": ("Projet 4 · Agent IA", "Projet 4 · AI Agent"),
    "key_set": ("Clé active ●", "Key active ●"),
    "no_key": ("⚠ Pas de clé — Settings", "⚠ No key — Settings"),
    "settings": ("⚙ Paramètres", "⚙ Settings"),
    "screen_info": ("🖥 Infos écran", "🖥 Screen info"),
    "web_page": ("🌐 Page locale", "🌐 Local page"),
    "web_failed": ("page locale indisponible", "local page unavailable"),
    "busy": ("⚠ Un run contrôle déjà la souris", "⚠ A run already owns the mouse"),
    "agent_mode": (" 🤖 Mode Agent ", " 🤖 Agent Mode "),
    "chat_mode": (" 💬 Mode Chat ", " 💬 Chat Mode "),
    "goal_box": (" Objectif de l'agent ", " Goal for the agent "),
    "run": ("▶ Lancer l'agent", "▶ Run Agent"),
    "stop": ("■ Arrêter", "■ Stop"),
    "idle": ("Prêt. L'agent analysera l'écran et contrôlera la souris/clavier.",
             "Ready. The agent will inspect your screen and control mouse/keyboard."),
    "running": ("En cours d'exécution…", "Running…"),
    "guidance_box": (" Consigne en direct (parler à l'agent) ",
                     " Direct guidance (talk to the agent) "),
    "send_guidance": ("Envoyer la consigne", "Send guidance"),
    "emergency": (" ⚠ Arrêt d'urgence ", " ⚠ Emergency stop "),
    "emergency_txt": ("Arrêt d'urgence : jette le curseur dans le coin HAUT-GAUCHE de l'écran.",
                      "Emergency stop: slam the mouse into the TOP-LEFT corner of the screen."),
    "session_log": (" Journal de session ", " Session log "),
    "live_panel": (" Activité en direct — ce que fait l'agent ",
                   " Live activity — what the agent does "),
    "game_box": (" 🎮 Mode jeu (Counter-Strike, FPS…) ", " 🎮 Game mode (Counter-Strike, FPS…) "),
    "game_hint": ("W/A/S/D maintenu, tir, visée relative — nécessite les droits administrateur.",
                  "Held W/A/S/D, fire, relative aim — requires administrator rights."),
    "window_box": (" 🪟 Capture par fenêtre ", " 🪟 Window capture "),
    "window_only": ("Ne capturer que cette fenêtre (jeu, app…)",
                    "Capture only this window (game, app…)"),
    "window_refresh": ("↻ Actualiser", "↻ Refresh"),
    "window_none": ("— aucune fenêtre détectée —", "— no window detected —"),
    "set_window_title": ("Titre de la fenêtre (sous-chaîne, vide = tout l'écran)",
                         "Window title (substring, empty = full screen)"),
    "presets_lbl": ("Exemples prêts à lancer :", "Ready-made goals:"),
    "presets_fr": [
        "Ouvre Brave",
        "Ouvre Brave et cherche « météo Paris »",
        "Ouvre le terminal PowerShell et affiche les processus (Get-Process)",
        "Recherche sur le web « IA actualités »",
        "Ouvre le Bloc-notes et écris « Bonjour, Agent Screen fonctionne ! »",
        "Ouvre l'Explorateur de fichiers depuis la barre des tâches",
        "Ouvre le menu Démarrer puis tape calculatrice et valide",
        "Réduis toutes les fenêtres (afficher le bureau)",
        "Prends une capture d'écran de tout l'écran (Win+Maj+S, plein écran)",
    ],
    "presets_en": [
        "Open Brave",
        "Open Brave and search for Paris weather",
        "Open PowerShell terminal and list processes (Get-Process)",
        "Search the web for AI news",
        "Open Notepad and type Hello, Agent Screen is working!",
        "Open File Explorer from the taskbar",
        "Open the Start menu, type calculator and press Enter",
        "Minimize all windows (show the desktop)",
        "Take a full-screen screenshot (Win+Shift+S, full screen)",
    ],
    "card_goal": ("Objectif", "Goal"),
    "thinking": ("Réflexion", "Thinking"),
    "command": ("Commande", "Command"),
    "after_action": ("Capture après action", "Screen after action"),
    "reached": ("✔ Objectif atteint", "✔ Goal reached"),
    "failed": ("✖ Erreur", "✖ Error"),
    "action_failed": ("Action échouée", "Action failed"),
    "your_guidance": ("Ta consigne", "Your guidance"),
    "guidance_not_sent": ("Aucun agent en cours d'exécution.", "No agent is currently running."),
    "dbl_click": ("Double-clic pour agrandir l'image", "Double-click to enlarge image"),
    "enter_goal": ("Écris d'abord un objectif à accomplir.", "Enter a goal first."),
    "still_running": ("L'agent est encore en cours d'exécution. Voulez-vous l'arrêter et quitter ?",
                      "The agent is still running. Stop it and quit?"),
    "attach": ("📸 Joindre une capture de mon écran", "📸 Attach a screenshot of my screen"),
    "send": ("Envoyer", "Send"),
    "clear_chat": ("Effacer l'historique", "Clear history"),
    "chat_wait": ("L'assistant analyse et prépare sa réponse…", "The assistant is thinking…"),
    "chat_intro": ("Pose une question ou coche la case pour analyser ce qui est affiché à l'écran.",
                   "Ask a question or check the box to analyze what's on screen."),
    "chat_error": ("Erreur du chat", "Chat error"),
    "chat_sys": ("Tu es Agent Screen, un assistant de bureau intelligent sur Windows. Sois clair, concis et serviable.",
                 "You are Agent Screen, an intelligent Windows desktop assistant. Be clear, concise and helpful."),
    "set_title": ("Paramètres & Clés API — Agent Screen", "Settings & API Keys — Agent Screen"),
    "provider": ("Fournisseur principal", "Primary AI provider"),
    "api_key_word": ("Clé", "Key"),
    "load_models": ("↻ Charger modèles", "↻ Load models"),
    "models_loaded": ("{n} modèles chargés avec succès ✅", "{n} models loaded successfully ✅"),
    "models_fail": ("Impossible de charger les modèles — vérifie la clé API.",
                    "Could not load models — verify your API key."),
    "models_hint": ("Choisis dans la liste ou tape un nom de modèle.",
                    "Pick from the list or type an exact model name."),
    "api_key": ("Clé API (stockée localement)", "API key (stored locally)"),
    "keys_hint": ("💡 Sépare plusieurs clés par une virgule pour un même fournisseur. L'agent bascule automatiquement si une clé atteint son quota.",
                  "💡 Separate multiple keys with commas for a provider. The agent will auto-fallback if quota is hit."),
    "model": ("Modèle IA", "AI Model"),
    "max_steps": ("Nombre maximal d'étapes par tâche", "Max steps per task"),
    "grid": ("Grille de coordonnées sur les captures (précision des clics)",
             "Coordinate grid on screenshots (click precision)"),
    "image_width": ("Résolution envoyée à l'IA (0 = native)", "Image width for the AI (0 = native)"),
    "game_mode": ("Mode jeu (touches scan-code + visée relative)",
                  "Game mode (raw scan-codes + relative aiming)"),
    "free_mouse": ("Libérer la souris entre chaque étape (rend le curseur)",
                   "Free mouse between steps (gives your cursor back)"),
    "step_delay": ("Délai d'attente entre les étapes (secondes)", "Delay between steps (seconds)"),
    "shots_each": ("Capture d'écran après chaque action individuelle",
                   "Screenshot after each individual action"),
    "language": ("Langue de l'interface / Language", "Interface language / Langue"),
    "save": ("Enregistrer les paramètres", "Save settings"),
    "test": ("Tester la connexion", "Test connection"),
    "close": ("Fermer", "Close"),
    "saved": ("Paramètres enregistrés ✔", "Settings saved ✔"),
    "saved_restart": ("Enregistré ✔ — Redémarrage de l'interface…", "Saved ✔ — Restarting UI…"),
    "testing": ("Test de connexion en cours…", "Testing connection…"),
    "test_ok": ("✅ Connexion réussie ({ms} ms) — Modèle : {model}\nRéponse : {reply}",
                "✅ Connection successful ({ms} ms) — Model: {model}\nReply: {reply}"),
    "footer": ("Clés enregistrées sur ce PC. Les messages et captures jointes sont envoyés au fournisseur IA utilisé.",
               "Keys are stored on this PC. Messages and attached screenshots are sent to the selected AI provider."),
    "get_key": ("Clé Gemini gratuite : https://aistudio.google.com/apikey",
                "Free Gemini key: https://aistudio.google.com/apikey"),
    "info_body": ("Écran principal : {w} × {h} pixels physiques\nDPI / Échelle   : {dpi} DPI ({scale}%)\n"
                  "Bureau virtuel  : {vw} × {vh} pixels (tous écrans)\nSystème OS       : {sys}",
                  "Primary screen : {w} × {h} physical pixels\nDPI / Scaling  : {dpi} DPI ({scale}%)\n"
                  "Virtual desktop: {vw} × {vh} pixels (all monitors)\nSystem OS       : {sys}"),
    "stopping": ("■ Arrêt demandé — finalisation de l'action…", "■ Stop requested — finishing current action…"),
    "failsafe": ("Failsafe déclenché (coin haut-gauche) — arrêt d'urgence.", "Failsafe triggered (top-left corner) — aborted."),
    "stopped": ("Exécution interrompue par l'utilisateur.", "Execution interrupted by user."),
    "shot_ask": ("Écran capturé — analyse de la situation…", "Screen captured — analyzing the situation…"),
    "step_done": ("Étape {i} terminée — nouvelle capture…", "Step {i} completed — capturing new screen…"),
    "max_steps_reached": ("Nombre maximal d'étapes atteint sans conclusion explicite.",
                          "Maximum steps reached without explicit completion."),
    "no_shot": ("(capture indisponible : {e})", "(screenshot unavailable: {e})"),
    "fallback_card": ("🔄 Bascule automatique : {from_p} ➔ {to_p}", "🔄 Auto-fallback: {from_p} ➔ {to_p}"),
    "img_widths": ["0", "960", "1280", "1600", "1920", "2560"],
}


def T(lang: str, key: str, **kw) -> str:
    val = S.get(key)
    if not val:
        return key
    if isinstance(val, (list, tuple)) and len(val) == 2 and isinstance(val[0], str) and isinstance(val[1], str):
        txt = val[0] if lang == "fr" else val[1]
    elif isinstance(val, (list, tuple)):
        return str(val)
    else:
        txt = str(val)
    return txt.format(**kw) if kw else txt


# ------------------------------------------------------------------- modern dark theme
BG = "#0c0e14"
CARD = "#141720"
CARD_HOVER = "#1a1f2b"
FIELD = "#0e1117"
LINE = "#202634"
TXT = "#f0f3f8"
MUT = "#8492a6"
MUT_LIGHT = "#a0aec0"
ACC = "#8b5cf6"
ACC_HOVER = "#a78bfa"
OK = "#10b981"
ERR = "#f43f5e"
WARN = "#f59e0b"
GAMEC = "#f97316"
FALLBACKC = "#a855f7"


def apply_dark_theme(root: tk.Tk):
    style = ttk.Style(root)
    for theme in ("clam",):
        if theme in style.theme_names():
            style.theme_use(theme)
    style.configure(".", background=BG, foreground=TXT, fieldbackground=FIELD,
                    bordercolor=LINE, lightcolor=CARD, darkcolor=CARD)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD, relief="flat")
    style.configure("TLabelframe", background=BG, bordercolor=LINE)
    style.configure("TLabelframe.Label", background=BG, foreground=MUT_LIGHT,
                    font=("Segoe UI", 9, "bold"))
    style.configure("TLabel", background=BG, foreground=TXT)
    style.configure("Card.TLabel", background=CARD, foreground=TXT)
    style.configure("TButton", background=CARD, foreground=TXT, bordercolor=LINE,
                    padding=(10, 5), font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", "#222735"), ("disabled", "#11141c")],
              foreground=[("disabled", "#505868")])
    style.configure("Accent.TButton", background=ACC, foreground="#ffffff",
                    font=("Segoe UI", 9, "bold"), bordercolor=ACC)
    style.map("Accent.TButton",
              background=[("active", ACC_HOVER), ("disabled", "#1e284a")],
              foreground=[("disabled", "#6c7a9c")])
    style.configure("Danger.TButton", background="#331418", foreground="#fca5a5",
                    font=("Segoe UI", 9, "bold"), bordercolor="#5c1f26")
    style.map("Danger.TButton",
              background=[("active", "#4d1b22"), ("disabled", "#1c0d10")],
              foreground=[("disabled", "#6c353c")])
    style.configure("TEntry", fieldbackground=FIELD, foreground=TXT,
                    insertcolor=TXT, bordercolor=LINE, padding=4)
    style.map("TEntry", bordercolor=[("focus", ACC)])
    style.configure("TCombobox", fieldbackground=FIELD, foreground=TXT,
                    background=CARD, bordercolor=LINE, arrowcolor=TXT, padding=3)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    style.configure("TSpinbox", fieldbackground=FIELD, foreground=TXT,
                    background=CARD, bordercolor=LINE, arrowcolor=TXT, padding=3)
    style.configure("TCheckbutton", background=BG, foreground=TXT, font=("Segoe UI", 9))
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TNotebook", background=BG, bordercolor=LINE)
    style.configure("TNotebook.Tab", background=CARD, foreground=MUT,
                    padding=(16, 8), font=("Segoe UI", 9, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", "#1c2230"), ("active", "#181d28")],
              foreground=[("selected", TXT), ("active", TXT)])
    style.configure("Vertical.TScrollbar", background=CARD, bordercolor=BG,
                    troughcolor=BG, arrowcolor=MUT)
    root.configure(background=BG)
    try:
        root.option_add("*TCombobox*Listbox.background", CARD)
        root.option_add("*TCombobox*Listbox.foreground", TXT)
        root.option_add("*TCombobox*Listbox.selectBackground", ACC)
    except Exception:
        pass


# --------------------------------------------------------------------- app
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load()
        self.lang = self.cfg.get("language", "fr")
        self.q: "queue.Queue[dict]" = queue.Queue()
        self.run: AgentRun | None = None
        self.restart_requested = False
        self._thumb_refs = []
        self._ghost = None
        self.overlay = None
        self.chat_history = []
        self.chat_conversations = conversations.load_all()
        self.chat_current = conversations.new_conversation()
        self.chat_sending = False
        self._chat_generation = 0
        self._web_starting = False

        root.title(f"⚡ {T(self.lang, 'app')} v{__version__}")
        root.geometry(f"1320x{min(880, root.winfo_screenheight() - 100)}")
        root.minsize(1100, 760)
        try:
            icon = _icon_path()
            if icon:
                root.iconbitmap(default=icon)
        except tk.TclError:
            pass

        apply_dark_theme(root)
        self._build_topbar()
        self._build_notebook()
        self._build_agent_tab()
        self._build_chat_tab()
        self._refresh_badge()
        self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _(self, key, **kw) -> str:
        return T(self.lang, key, **kw)

    # ------------------------------------------------------------ top bar
    def _build_topbar(self):
        bar = ttk.Frame(self.root, padding=(16, 10))
        bar.pack(fill="x")

        # Brand
        title_box = ttk.Frame(bar)
        title_box.pack(side="left")
        ttk.Label(title_box, text="✦ Projet 4 · Agent IA", font=("Segoe UI", 16, "bold"),
                  foreground="#ffffff").pack(side="left")
        ttk.Label(title_box, text=f" v{__version__}", font=("Segoe UI", 9),
                  foreground=MUT).pack(side="left", padx=(4, 14))

        # Status pills
        self.badge = ttk.Label(bar, text="", foreground=MUT_LIGHT,
                               font=("Segoe UI", 9, "bold"))
        self.badge.pack(side="left", padx=4)

        self.fallback_pill = ttk.Label(bar, text="", foreground=FALLBACKC,
                                       font=("Segoe UI", 9, "bold"))
        self.fallback_pill.pack(side="left", padx=8)

        self.game_banner = ttk.Label(bar, text="", foreground=GAMEC,
                                     font=("Segoe UI", 9, "bold"))
        self.game_banner.pack(side="left", padx=4)

        # Right buttons
        ttk.Button(bar, text=self._("settings"), style="TButton",
                   command=self._open_settings).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=self._("screen_info"), style="TButton",
                   command=self._show_screen_info).pack(side="right")
        # Native app navigation stays in this window.

    def _refresh_badge(self):
        self.cfg = load()
        self.lang = self.cfg.get("language", self.lang)
        p = self.cfg.get("provider", "gemini")
        keys = get_provider_keys(p)
        key_ok = len(keys) > 0 or p in LOCAL_PROVIDERS
        mark = "Local · sans clé requise" if p in LOCAL_PROVIDERS else self._('key_set') if key_ok else self._('no_key')
        p_name = PROVIDER_LABELS.get(p, p)
        model = self.cfg.get("models", {}).get(p, "")
        self.badge.config(
            text=f"{p_name}  ·  {mark}",
            foreground=OK if key_ok else WARN,
        )

        marks = []
        if self.cfg.get("game_mode"):
            marks.append("🎮 " + ("MODE JEU ACTIF" if self.lang == "fr" else "GAME MODE ON"))
        if self.cfg.get("window_mode") and self.cfg.get("window_title"):
            marks.append(f"🪟 {self.cfg['window_title']}")
        self.game_banner.config(text="   ".join(marks))

    def _set_fallback_badge(self, prov_name: str):
        self.fallback_pill.config(text=f"🔄 Fallback: {prov_name}")

    # ------------------------------------------------------------ notebook
    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(2, 12))
        self.tab_agent = ttk.Frame(self.nb, padding=10)
        self.tab_chat = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab_agent, text=self._("agent_mode"))
        self.nb.add(self.tab_chat, text=self._("chat_mode"))

    # ------------------------------------------------------------ agent tab
    def _build_agent_tab(self):
        tab = self.tab_agent
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)

        hero = tk.Frame(left, bg="#211a36", highlightbackground="#49346d", highlightthickness=1)
        hero.pack(fill="x", pady=(0, 10))
        tk.Label(hero, text="Votre objectif. Son prochain mouvement.", bg="#211a36", fg="#ede9fe",
                 font=("Segoe UI", 15, "bold"), anchor="w", padx=14, pady=10).pack(fill="x")
        tk.Label(hero, text="Bureau ou navigateur · IA cloud ou locale · actions visibles", bg="#211a36",
                 fg="#b8aaca", anchor="w", padx=14, pady=4).pack(fill="x")

        # -- Goal Box
        box = ttk.LabelFrame(left, text=f" {self._('goal_box')} ", padding=10)
        box.pack(fill="x")
        box.columnconfigure(0, weight=1)

        self.goal_entry = ttk.Entry(box, font=("Segoe UI", 11))
        self.goal_entry.grid(row=0, column=0, sticky="ew")
        self.goal_entry.bind("<Return>", lambda e: self._start_run())

        preset_row = ttk.Frame(box)
        preset_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(preset_row, text=self._("presets_lbl"), foreground=MUT).pack(side="left")
        self.preset_cb = ttk.Combobox(
            preset_row,
            state="readonly",
            values=S["presets_fr"] if self.lang == "fr" else S["presets_en"],
        )
        self.preset_cb.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self.preset_cb.bind("<<ComboboxSelected>>", self._on_preset)

        btns = ttk.Frame(box)
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.run_btn = ttk.Button(btns, text=self._("run"), style="Accent.TButton",
                                  command=self._start_run)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text=self._("stop"), style="Danger.TButton",
                                   command=self._stop_run, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        self.status_lbl = ttk.Label(btns, text=self._("idle"), foreground=MUT_LIGHT,
                                    wraplength=340, justify="left")
        self.status_lbl.pack(side="left", padx=(10, 0))

        # -- Game Mode
        game_box = ttk.LabelFrame(left, text=" 01 · Espace de travail ", padding=8)
        game_box.pack(fill="x", pady=(10, 0))
        game_box.columnconfigure(0, weight=1)
        game_row = ttk.Frame(game_box)
        game_row.grid(row=0, column=0, sticky="ew")
        self.mode_var = tk.StringVar(value=self.cfg.get("execution_mode", "desktop"))
        ttk.Radiobutton(game_row, text="Bureau", value="desktop", variable=self.mode_var,
                        command=self._save_run_options).pack(side="left", padx=4)
        ttk.Radiobutton(game_row, text="Navigateur uniquement", value="browser", variable=self.mode_var,
                        command=self._save_run_options).pack(side="left", padx=8)
        self.eco_var = tk.BooleanVar(value=self.cfg.get("eco_mode", False))
        ttk.Checkbutton(game_row, text="Éco", variable=self.eco_var,
                        command=self._save_run_options).pack(side="right")
        self.profile_var = tk.StringVar(value=self.cfg.get("agent_profile", "general"))
        profile_row = ttk.Frame(game_box)
        profile_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(profile_row, text="Profil :", foreground=MUT).pack(side="left")
        ttk.Radiobutton(profile_row, text="Général", value="general", variable=self.profile_var,
                        command=self._save_run_options).pack(side="left", padx=5)
        ttk.Radiobutton(profile_row, text="Montage vidéo", value="video_editing", variable=self.profile_var,
                        command=self._save_run_options).pack(side="left", padx=5)
        self.autonomous_var = tk.BooleanVar(value=self.cfg.get("autonomous_mode", False))
        ttk.Checkbutton(profile_row, text="Autonome", variable=self.autonomous_var,
                        command=self._save_run_options).pack(side="right")
        options = ttk.Frame(game_box)
        options.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.cursor_var = tk.BooleanVar(value=self.cfg.get("virtual_cursor", True))
        ttk.Checkbutton(options, text="Curseur IA visible", variable=self.cursor_var,
                        command=self._save_run_options).pack(side="left")
        self.game_var = tk.BooleanVar(value=bool(self.cfg.get("game_mode")))
        ttk.Checkbutton(options, text="Touches jeu (bureau)", variable=self.game_var,
                        command=self._toggle_game).pack(side="left")
        limits = ttk.Frame(game_box)
        limits.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.limit_var = tk.BooleanVar(value=self.cfg.get("limit_actions_per_capture", True))
        ttk.Checkbutton(limits, text="Limiter les actions par capture", variable=self.limit_var,
                        command=self._save_run_options).pack(side="left")
        self.action_count = ttk.Spinbox(limits, from_=1, to=12, width=4, command=self._save_run_options)
        self.action_count.set(self.cfg.get("actions_per_capture", 3))
        self.action_count.pack(side="left", padx=8)
        self.action_count.bind("<FocusOut>", lambda e: self._save_run_options())
        ttk.Label(game_box, text="Éco : captures 960 px / JPEG 60, contexte court, sans captures intermédiaires.",
                  foreground=MUT, wraplength=490).grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Label(game_box, text="Autonome : veille locale gratuite, réveil sur message/changement, budget borné.",
                  foreground=MUT, wraplength=490).grid(row=5, column=0, sticky="w", pady=(2, 0))

        # -- Window Capture
        win_box = ttk.LabelFrame(left, text=self._("window_box"), padding=10)
        win_box.pack(fill="x", pady=(10, 0))
        win_box.columnconfigure(0, weight=1)
        self.win_var = tk.BooleanVar(value=bool(self.cfg.get("window_mode")))
        ttk.Checkbutton(win_box, text=self._("window_only"), variable=self.win_var,
                        command=self._toggle_window).grid(row=0, column=0, sticky="w")
        ttk.Button(win_box, text=self._("window_refresh"), style="TButton",
                   command=self._refresh_windows).grid(row=0, column=1, sticky="e")
        self.win_cb = ttk.Combobox(win_box, state="readonly")
        self.win_cb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.win_cb.bind("<<ComboboxSelected>>", self._on_window_selected)
        self._win_titles = []
        self.win_selected = self.cfg.get("window_title", "")
        self._refresh_windows()

        # -- Guidance
        guide_box = ttk.LabelFrame(left, text=f" {self._('guidance_box')} ", padding=10)
        guide_box.pack(fill="x", pady=(10, 0))
        guide_box.columnconfigure(0, weight=1)
        self.guide_entry = ttk.Entry(guide_box)
        self.guide_entry.grid(row=0, column=0, sticky="ew")
        self.guide_entry.bind("<Return>", lambda e: self._send_guidance())
        self.guide_btn = ttk.Button(guide_box, text=self._("send_guidance"),
                                    style="TButton", command=self._send_guidance, state="disabled")
        self.guide_btn.grid(row=0, column=1, padx=(8, 0))

        # -- Emergency stop notice
        hint = ttk.Frame(left)
        hint.pack(fill="x", pady=(8, 0))
        ttk.Label(hint, foreground=ERR, text="🚨 " + self._("emergency_txt"),
                  wraplength=460, justify="left", font=("Segoe UI", 9, "bold")).pack(fill="x")

        # -- Session Log
        log_box = ttk.LabelFrame(left, text=f" {self._('session_log')} ", padding=6)
        log_box.pack(fill="both", expand=True, pady=(6, 0))
        self.log = tk.Text(log_box, height=5, wrap="word", state="disabled",
                           font=("Consolas", 9), background=FIELD, foreground="#c8d0e0",
                           relief="flat", padx=8, pady=6, insertbackground=TXT)
        log_scroll = ttk.Scrollbar(log_box, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # -- Live Activity Panel (Right side)
        right = ttk.LabelFrame(tab, text=f" {self._('live_panel')} ", padding=6)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(right, highlightthickness=0, background="#090b0f")
        self.scroll = ttk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.inner = ttk.Frame(self.canvas)
        self.inner_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._add_card("✦ Votre copilote est prêt", "Décrivez une tâche, choisissez votre espace de travail, puis lancez l’agent.\n\nSes actions et captures apparaîtront ici.", color=MUT_LIGHT)

    def _save_run_options(self):
        try:
            count = int(self.action_count.get()) if hasattr(self, "action_count") else 3
            save({"execution_mode": self.mode_var.get(), "eco_mode": self.eco_var.get(),
                  "agent_profile": self.profile_var.get(), "autonomous_mode": self.autonomous_var.get(),
                  "virtual_cursor": self.cursor_var.get(), "limit_actions_per_capture": self.limit_var.get(),
                  "actions_per_capture": count})
            self.cfg.update(load())
        except (ValueError, tk.TclError):
            if hasattr(self, "action_count"):
                self.action_count.set(load()["actions_per_capture"])

    def _on_inner_configure(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfigure(self.inner_win, width=e.width)

    def _on_mousewheel(self, e):
        widget = self.root.winfo_containing(e.x_root, e.y_root)
        while widget is not None:
            if widget is self.canvas:
                self.canvas.yview_scroll(-1 * (e.delta // 120), "units")
                break
            widget = getattr(widget, "master", None)

    # -- Ghost cursor
    def _show_ghost(self, x: int, y: int):
        if self.overlay:
            self.overlay.show(x, y, True)

    def _on_preset(self, _e=None):
        val = self.preset_cb.get()
        if val:
            self.goal_entry.delete(0, "end")
            self.goal_entry.insert(0, val)
            self._start_run()

    def _toggle_game(self):
        save({"game_mode": bool(self.game_var.get())})
        self._refresh_badge()

    def _refresh_windows(self):
        self._win_titles = []
        items = []
        # display owns "which windows are capturable"; the dotted-title filter
        # below only hides internal overlay windows from the picker.
        for w in display.interesting_windows(0):
            t = w["title"]
            self._win_titles.append(t)
            items.append(f"{t}  ({w['w']}x{w['h']})")
        self.win_cb.config(values=items or [self._("window_none")])
        idx = -1
        if self.win_selected:
            for n, t in enumerate(self._win_titles):
                if t == self.win_selected:
                    idx = n
                    break
        if idx >= 0:
            self.win_cb.current(idx)
        elif items:
            self.win_cb.current(0)
            self.win_selected = self._win_titles[0]
        else:
            self.win_cb.set(self._("window_none"))
            self.win_selected = ""

    def _on_window_selected(self, _e=None):
        idx = self.win_cb.current()
        if 0 <= idx < len(self._win_titles):
            self.win_selected = self._win_titles[idx]
            if self.win_var.get():
                save({"window_title": self.win_selected})
            self._refresh_badge()

    def _toggle_window(self):
        if self.win_var.get():
            self._refresh_windows()
        save({"window_mode": bool(self.win_var.get()),
              "window_title": self.win_selected if self.win_var.get() else ""})
        self._refresh_badge()

    # -- Activity Cards with colored left accent borders
    def _add_card(self, title: str, body: str = "", color: str = TXT, accent: str = ACC) -> ttk.Frame:
        card = tk.Frame(self.inner, background=CARD, padx=0, pady=0,
                        highlightthickness=1, highlightbackground=LINE)
        card.pack(fill="x", padx=6, pady=5)

        # Left border bar
        bar = tk.Frame(card, background=accent, width=4)
        bar.pack(side="left", fill="y")

        content = tk.Frame(card, background=CARD, padx=10, pady=8)
        content.pack(side="left", fill="both", expand=True)

        tk.Label(content, text=title, font=("Segoe UI", 9, "bold"),
                 background=CARD, foreground=accent).pack(anchor="w")

        if body:
            tk.Label(content, text=body, font=("Segoe UI", 9),
                     background=CARD, foreground=color, wraplength=420,
                     justify="left").pack(anchor="w", pady=(3, 0))

        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)
        return card

    def _add_shot_card(self, title: str, b64_png: str):
        card = self._add_card(title, accent="#38bdf8")
        try:
            img = Image.open(io.BytesIO(base64.b64decode(b64_png)))
            thumb = img.copy()
            thumb.thumbnail((390, 230))
            photo = ImageTk.PhotoImage(thumb)
            self._thumb_refs.append(photo)

            lbl = tk.Label(card, image=photo, background=CARD, cursor="hand2")
            lbl.pack(padx=10, pady=(0, 4))

            def enlarge(_e, img=img):
                win = tk.Toplevel(self.root)
                win.title("Agent Screen — Capture d'écran")
                big = img.copy()
                big.thumbnail((1100, 720))
                ph = ImageTk.PhotoImage(big)
                lbl2 = tk.Label(win, image=ph, background="#000")
                lbl2.image = ph
                lbl2.pack()
                win.geometry(f"{big.width}x{big.height}")

            lbl.bind("<Double-Button-1>", enlarge)
            tk.Label(card, text=self._("dbl_click"), font=("Segoe UI", 8),
                     background=CARD, foreground=MUT).pack(pady=(0, 4))
        except Exception as e:
            tk.Label(card, text=self._("no_shot", e=e), font=("Segoe UI", 9),
                     background=CARD, foreground=ERR).pack(pady=4)

    # -- Agent controls
    def _start_run(self):
        # <Return> in the goal field and the preset list call this directly, so they
        # bypass the disabled Run button; and the local page can hold a run too. The
        # owner module decides, so no surface can put a second agent on the mouse.
        if agent.active_run() is not None:
            self.status_lbl.config(text=self._("busy"), foreground=WARN)
            self._log(self._("busy"))
            return
        goal = self.goal_entry.get().strip()
        if not goal:
            messagebox.showinfo(T(self.lang, "app"), T(self.lang, "enter_goal"))
            return
        self._save_run_options()
        cfg = load()
        if cfg["provider"] not in LOCAL_PROVIDERS and not get_api_key(cfg["provider"]) and not get_available_providers():
            # say why: the settings window opening on its own is not an explanation
            self.status_lbl.config(text=self._("no_key"), foreground=WARN)
            self._log(self._("no_key"))
            self._open_settings()
            return

        # Clean prior activity
        for w in self.inner.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        self.fallback_pill.config(text="")

        self._add_card(T(self.lang, "card_goal"), goal, color="#93c5fd", accent=ACC)
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.guide_btn.config(state="normal")
        self.status_lbl.config(text=T(self.lang, "running"), foreground=ACC)

        run = None
        try:
            run = AgentRun(
                goal, cfg["provider"], max_steps=cfg["max_steps"],
                grid=cfg.get("grid", True), image_width=cfg.get("image_width", 1280),
                game_mode=cfg.get("game_mode", False), step_delay=cfg.get("step_delay", 0.4),
                screenshot_each_action=cfg.get("screenshot_each_action", False),
                window_mode=cfg.get("window_mode", False),
                window_title=cfg.get("window_title", ""),
                lang=self.lang, free_mouse=cfg.get("free_mouse", True),
                jpeg_quality=cfg.get("jpeg_quality", 80), emit=self._emit,
                execution_mode=cfg["execution_mode"], eco_mode=cfg["eco_mode"],
                actions_per_capture=cfg["actions_per_capture"],
                limit_actions_per_capture=cfg["limit_actions_per_capture"],
                virtual_cursor=cfg["virtual_cursor"], agent_profile=cfg["agent_profile"],
                autonomous_mode=cfg["autonomous_mode"],
                autonomous_minutes=cfg["autonomous_minutes"],
                autonomous_max_calls=cfg["autonomous_max_calls"],
                autonomous_min_interval=cfg["autonomous_min_interval"])
            self.run = run
            # claim before starting the thread: the run owns the mouse from here, so
            # the poller can tell a live run from a dead one without a race
            agent.claim(run)
            if self.overlay is None:
                self.overlay = AgentOverlay(self.root, self._stop_run, self._overlay_message)
            mode_label = "Montage" if cfg["agent_profile"] == "video_editing" else (
                "Navigateur" if cfg["execution_mode"] == "browser" else "Bureau")
            if cfg["autonomous_mode"]:
                mode_label += " · Autonome"
            self.overlay.start(mode_label)
            threading.Thread(target=run.run, daemon=True).start()
        except agent.RunBusy:      # the local page took the mouse in between
            self.run = None
            self._finish("⏹")
            self.status_lbl.config(text=self._("busy"), foreground=WARN)
            self._log(self._("busy"))
        except Exception as e:  # noqa: BLE001 - never leave the buttons frozen
            agent.release(run)     # a thread that never started must not keep it
            self.run = None
            self._add_card(T(self.lang, "failed"), f"{type(e).__name__}: {e}",
                           color=ERR, accent=ERR)
            self._finish("✖")

    def _stop_run(self):
        if self.run:
            self.run.stop()
            self._log("■ " + T(self.lang, "stopping"))

    def _send_guidance(self):
        text = self.guide_entry.get().strip()
        if not text:
            return
        self.guide_entry.delete(0, "end")
        if self.run and not self.run.stopped:
            self.run.guide(text)
            self._add_card(T(self.lang, "your_guidance"), text, color=OK, accent=OK)
            self._log(f"🗨 {text}")
        else:
            self._add_card(T(self.lang, "your_guidance"),
                           T(self.lang, "guidance_not_sent"), color=ERR, accent=ERR)

    def _overlay_message(self, text):
        if self.run and not self.run.stopped:
            self.run.guide(text)
            self._add_card("Message depuis le bandeau", text, color=OK, accent=OK)
            self._log(f"Bandeau : {text}")

    def _emit(self, event, **kw):
        self.q.put({"event": event, **kw})

    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self._handle_event(msg)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        # a run claiming the mouse is the truth: if the thread died without emitting
        # 'finished', this is what stops the Run button from staying dead forever
        if self.run is not None and agent.active_run() is None:
            self._finish("⏹")
        try:
            self.root.after(80, self._pump)
        except tk.TclError:
            pass

    def _handle_event(self, msg):
        ev = msg["event"]
        if ev == "ui_callback":
            if _alive(msg["window"]):
                msg["callback"]()
        elif ev == "cursor":
            try:
                if self.overlay and self.run:
                    self.overlay.show(msg["x"], msg["y"], msg.get("click", False))
                    self.root.update_idletasks()
            finally:
                msg["ready"].set()
        elif ev == "thought":
            if self.overlay:
                self.overlay.status(f"Étape {msg['step']} · Analyse")
            self._add_card(f"💭 {msg['step']} · {self._('thinking')}", msg["text"],
                           color=TXT, accent=ACC)
            self._log(f"step {msg['step']}: {msg['text'][:100]}")
            if self.overlay:
                self.overlay.message("IA : " + msg["text"])
        elif ev == "action":
            args = ", ".join(f"{k}={v}" for k, v in msg["args"].items())
            hold = f"  [hold {msg['hold']}s]" if msg.get("hold") else ""
            color = GAMEC if msg.get("game") else WARN
            title = f"⚡ {msg['step']}.{msg.get('sub', 1)} · {self._('command')}"
            self._add_card(title, f"{msg['name']}({args}){hold}", color=color, accent=color)
            if self.overlay:
                self.overlay.status(f"{msg['step']}.{msg.get('sub', 1)} · {msg['name']}")
            self._log(f"step {msg['step']}.{msg.get('sub', 1)}: {msg['name']}({args}){hold}")
        elif ev == "screenshot":
            sub = f".{msg['sub']}" if msg.get("sub") else ""
            self._add_shot_card(f"📸 {msg['step']}{sub} · {self._('after_action')}", msg["image"])
        elif ev == "motion":
            self._add_card("Séquence observée", f"{len(msg['frames'])} images sur {msg['seconds']:.1f} secondes",
                           color="#38bdf8", accent="#38bdf8")
        elif ev == "video":
            self._add_card("🎬 Clip enregistré",
                           f"{msg['file']} · {msg['seconds']} s\n{msg['path']}",
                           color="#38bdf8", accent="#38bdf8")
            self._log(f"🎬 {msg['path']}")
        elif ev == "autonomous_wait":
            text = f"Veille locale · {msg['calls']}/{msg['budget']} appels IA"
            self.status_lbl.config(text=text, foreground=OK)
            if self.overlay:
                self.overlay.status(text)
        elif ev == "autonomous_limit":
            self._add_card("Budget autonome terminé",
                           f"Arrêt après {msg['calls']} appels IA. Relance si tu veux continuer.",
                           color=WARN, accent=WARN)
            if self.overlay:
                self.overlay.message(f"Budget terminé : {msg['calls']} appels IA.")
        elif ev == "fallback":
            from_p = PROVIDER_LABELS.get(msg.get("from_provider"), msg.get("from_provider"))
            to_p = PROVIDER_LABELS.get(msg.get("to_provider"), msg.get("to_provider"))
            reason = msg.get("reason", "")
            title = "🔄 Bascule IA / Auto-Fallback"
            body = f"{from_p} ➔ {to_p}"
            if reason:
                body += f"\nRaison : {reason[:120]}"
            self._add_card(title, body, color=FALLBACKC, accent=FALLBACKC)
            self._log(f"🔄 Bascule automatique : {from_p} -> {to_p}")
            self._set_fallback_badge(to_p)
        elif ev == "done":
            self._add_card(T(self.lang, "reached"), msg["text"], color=OK, accent=OK)
            self._log("✔ " + msg["text"])
        elif ev == "error":
            self._add_card(T(self.lang, "failed"), msg["text"], color=ERR, accent=ERR)
            self._log("✖ " + msg["text"])
        elif ev == "action_error":
            self._add_card(T(self.lang, "action_failed"), msg["text"], color=ERR, accent=ERR)
        elif ev == "finished":
            outcome = msg.get("outcome", "done")
            if outcome == "done":
                self._finish("✔")
            elif outcome == "stopped":
                self._add_card("Arrêté", self._("stopped"), color=WARN, accent=WARN)
                self._finish("⏹")
            elif outcome == "max_steps":
                self._add_card("Limite", self._("max_steps_reached"), color=WARN, accent=WARN)
                self._finish("⚠")
            elif outcome == "autonomous_limit":
                self._finish("⚠")
            else:
                self._finish("✖")
        elif ev == "chat_reply":
            if msg.get("generation", self._chat_generation) != self._chat_generation:
                return
            is_error = bool(msg.get("error"))
            text = msg.get("text", "") or ("(réponse vide)" if self.lang == "fr" else "(empty reply)")
            eff_p = msg.get("provider", "")
            prov_tag = f" [{PROVIDER_LABELS.get(eff_p, eff_p)}]" if eff_p else ""
            if not is_error:
                self.chat_history.append(("assistant", text, eff_p))
                self._chat_append(f"🤖 Projet 4{prov_tag}", text, "assistant")
                self._persist_chat()
            else:
                if self.chat_history and self.chat_history[-1][0] == "user":
                    self.chat_history.pop()
                    if self.chat_history:
                        self._persist_chat()
                    else:
                        conversations.delete(self.chat_current["id"])
                        self._refresh_chat_list(False)
                self._chat_append(T(self.lang, "chat_error"), text, "error")

            self.chat_sending = False
            self.chat_send.config(state="normal")
            self.chat_entry.config(state="normal")
            self.chat_status.config(text=T(self.lang, "chat_intro"),
                                    foreground=ERR if is_error else MUT)
            self.chat_entry.focus_set()
        elif ev == "status":
            key = msg.get("key")
            if key == "step_done":
                self._log(self._("step_done", i=msg.get("i", "")))
            elif key and key in S:
                self._log(self._(key))
            else:
                self._log(str(msg.get("text", "")))

    def _finish(self, mark: str):
        if self.overlay:
            self.overlay.finish()
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.guide_btn.config(state="disabled")
        status_txt = "Terminé avec succès" if mark == "✔" else "Arrêté / Erreur"
        self.status_lbl.config(
            text=f"{mark} {status_txt if self.lang == 'fr' else 'Completed' if mark == '✔' else 'Stopped/Error'}",
            foreground=OK if mark == "✔" else WARN if mark in ("⏹", "⚠") else ERR,
        )
        self.run = None

    def _log(self, text: str):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ------------------------------------------------------------ chat tab
    def _build_chat_tab(self):
        tab = self.tab_chat
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(tab, width=260, padding=(0, 0, 10, 0))
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sidebar.grid_propagate(False)
        ttk.Label(sidebar, text="Discussions", font=("Segoe UI", 12, "bold"),
                  foreground=TXT).pack(anchor="w", pady=(4, 8))
        ttk.Button(sidebar, text="＋ Nouvelle discussion", style="Accent.TButton",
                   command=self._new_chat).pack(fill="x", pady=(0, 8))
        self.chat_list = tk.Listbox(sidebar, width=33, background=CARD, foreground=TXT,
                                    selectbackground=ACC, selectforeground="white", relief="flat",
                                    highlightthickness=1, highlightbackground=LINE,
                                    font=("Segoe UI", 9), activestyle="none")
        self.chat_list.pack(fill="both", expand=True)
        self.chat_list.bind("<<ListboxSelect>>", self._open_selected_chat)
        side_actions = ttk.Frame(sidebar)
        side_actions.pack(fill="x", pady=(8, 0))
        self.chat_favorite_btn = ttk.Button(side_actions, text="☆ Favori", command=self._toggle_chat_favorite)
        self.chat_favorite_btn.pack(side="left", expand=True, fill="x")
        ttk.Button(side_actions, text="Supprimer", command=self._delete_chat).pack(
            side="left", expand=True, fill="x", padx=(6, 0))
        self.chat_cost = ttk.Label(sidebar, text="Mode éco Chat actif", foreground=OK,
                                   wraplength=240, justify="left")
        self.chat_cost.pack(anchor="w", pady=(8, 0))

        self.chat_view = tk.Text(tab, wrap="word", state="disabled",
                                 font=("Segoe UI", 10), background=FIELD, foreground=TXT,
                                 padx=18, pady=16, insertbackground=TXT, relief="flat",
                                 spacing1=2, spacing3=10)
        self.chat_view.tag_configure("user_hdr", foreground="#60a5fa", font=("Segoe UI", 10, "bold"), spacing1=12)
        self.chat_view.tag_configure("bot_hdr", foreground="#34d399", font=("Segoe UI", 10, "bold"), spacing1=12)
        self.chat_view.tag_configure("err_hdr", foreground=ERR, font=("Segoe UI", 10, "bold"), spacing1=12)
        self.chat_view.tag_configure("body", foreground="#f1f5f9", font=("Segoe UI", 10), spacing3=6)

        scroll = ttk.Scrollbar(tab, command=self.chat_view.yview)
        self.chat_view.configure(yscrollcommand=scroll.set)
        self.chat_view.grid(row=0, column=1, sticky="nsew")
        scroll.grid(row=0, column=2, sticky="ns")

        bottom = ttk.Frame(tab)
        bottom.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(0, weight=1)

        self.chat_status = ttk.Label(bottom, text=T(self.lang, "chat_intro"), foreground=MUT)
        self.chat_status.grid(row=0, column=0, sticky="w")

        self.attach_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text=T(self.lang, "attach"),
                        variable=self.attach_var).grid(row=0, column=1, sticky="e")
        ttk.Button(bottom, text="Nouvelle", style="TButton",
                   command=self._new_chat).grid(row=0, column=2, padx=(10, 0))

        entry_row = ttk.Frame(bottom)
        entry_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        entry_row.columnconfigure(0, weight=1)

        self.chat_entry = ttk.Entry(entry_row, font=("Segoe UI", 11))
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self._send_chat())

        self.chat_send = ttk.Button(entry_row, text=T(self.lang, "send"),
                                    style="Accent.TButton", command=self._send_chat)
        self.chat_send.grid(row=0, column=1, padx=(8, 0))
        self._refresh_chat_list()

    def _refresh_chat_list(self, select_current=True):
        if not hasattr(self, "chat_list"):
            return
        self.chat_conversations = conversations.load_all()
        self.chat_list.delete(0, "end")
        current_index = None
        for i, item in enumerate(self.chat_conversations):
            self.chat_list.insert("end", ("★ " if item["favorite"] else "   ") + item["title"])
            if item["id"] == self.chat_current["id"]:
                current_index = i
        if select_current and current_index is not None:
            self.chat_list.selection_set(current_index)
            self.chat_list.see(current_index)
        self.chat_favorite_btn.config(text="★ Favori" if self.chat_current["favorite"] else "☆ Favori")

    def _persist_chat(self):
        if not self.chat_history:
            return
        self.chat_current["messages"] = [
            {"role": role, "text": text, "provider": provider}
            for role, text, provider in self.chat_history
        ]
        self.chat_current = conversations.save_conversation(self.chat_current)
        self._refresh_chat_list()

    def _render_chat(self):
        self.chat_view.config(state="normal")
        self.chat_view.delete("1.0", "end")
        self.chat_view.config(state="disabled")
        for role, text, provider in self.chat_history:
            if role == "user":
                self._chat_append("Vous" if self.lang == "fr" else "You", text, "user")
            else:
                tag = f" [{PROVIDER_LABELS.get(provider, provider)}]" if provider else ""
                self._chat_append(f"🤖 Projet 4{tag}", text, "assistant")

    def _new_chat(self):
        self._persist_chat()
        self._chat_generation += 1
        self.chat_current = conversations.new_conversation()
        self.chat_history = []
        self.chat_sending = False
        self.chat_send.config(state="normal")
        self.chat_entry.config(state="normal")
        self._render_chat()
        self._refresh_chat_list(False)
        self.chat_status.config(text=T(self.lang, "chat_intro"), foreground=MUT)

    def _open_selected_chat(self, _event=None):
        selected = self.chat_list.curselection()
        if not selected or self.chat_sending:
            return
        target = self.chat_conversations[selected[0]]
        if target["id"] == self.chat_current["id"]:
            return
        self._persist_chat()
        self._chat_generation += 1
        self.chat_current = target
        self.chat_history = [(m["role"], m["text"], m.get("provider", ""))
                             for m in target["messages"]]
        self._render_chat()
        self._refresh_chat_list()

    def _toggle_chat_favorite(self):
        if not self.chat_history:
            return
        self.chat_current["favorite"] = not self.chat_current["favorite"]
        self._persist_chat()

    def _delete_chat(self):
        if not self.chat_history:
            return
        conversations.delete(self.chat_current["id"])
        self.chat_current = conversations.new_conversation()
        self.chat_history = []
        self._render_chat()
        self._refresh_chat_list(False)

    def _chat_append(self, who: str, text: str, tag: str = "assistant"):
        self.chat_view.config(state="normal")
        hdr_tag = "user_hdr" if tag == "user" else "bot_hdr" if tag == "assistant" else "err_hdr"
        self.chat_view.insert("end", f"{who}\n", hdr_tag)
        self.chat_view.insert("end", f"{text}\n\n", "body")
        self.chat_view.see("end")
        self.chat_view.config(state="disabled")

    def _clear_chat(self):
        self._new_chat()

    def _send_chat(self):
        if self.chat_sending:
            return
        text = self.chat_entry.get().strip()
        if not text:
            return
        cfg = load()
        if cfg["provider"] not in LOCAL_PROVIDERS and not get_api_key(cfg["provider"]) and not get_available_providers():
            self.chat_status.config(text=T(self.lang, "no_key"), foreground=WARN)
            self._open_settings()
            return

        self.chat_sending = True
        self.chat_entry.delete(0, "end")
        user_lbl = "Vous" if self.lang == "fr" else "You"
        if self.attach_var.get():
            user_lbl += " 📸"
        self._chat_append(user_lbl, text, "user")
        self.chat_history.append(("user", text, ""))
        if len(self.chat_history) == 1:
            self.chat_current["title"] = conversations.title_from(text)
        self._persist_chat()

        with_shot = self.attach_var.get()
        self.chat_send.config(state="disabled")
        self.chat_entry.config(state="disabled")
        self.chat_status.config(text=T(self.lang, "chat_wait"), foreground=ACC)

        keep = cfg.get("chat_context_messages", 6) if cfg.get("chat_eco", True) else 10
        recent = self.chat_history[-(keep + 1):]
        generation = self._chat_generation

        def worker():
            b64 = None
            mime = "image/jpeg"
            if with_shot:
                try:
                    b64 = display.take_screenshot(grid=False, max_width=1280, jpeg_quality=80)
                    mime = "image/jpeg"
                except Exception:
                    b64 = None

            try:
                if len(recent) <= 1:
                    prompt = text
                else:
                    history_lines = []
                    for role, msg, _provider in recent[:-1]:
                        speaker = "Utilisateur" if role == "user" else "Assistant"
                        history_lines.append(f"{speaker}: {msg}")
                    prompt = (
                        "Historique de la conversation :\n"
                        + "\n".join(history_lines)
                        + f"\n\nNouveau message de l'utilisateur : {text}"
                    )

                reply, eff_prov = chat_with_fallback(
                    cfg["provider"],
                    prompt=prompt,
                    system=T(cfg.get("language", "fr"), "chat_sys"),
                    b64_png=b64,
                    mime=mime,
                    max_tokens=cfg.get("chat_response_tokens", 700) if cfg.get("chat_eco", True) else 2048,
                )
                self.q.put({"event": "chat_reply", "text": reply, "error": False,
                            "provider": eff_prov, "generation": generation})
            except Exception as e:
                self.q.put({"event": "chat_reply", "text": str(e), "error": True,
                            "generation": generation})

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ settings
    def _open_local_page(self):
        """Open the local page that ships with the app. The installer creates no
        shortcut for it, so this button is the way in from the installed exe.
        server.start() binds the port before we open the browser."""
        url = f"http://{server.HOST}:{server.PORT}/"
        if self._web_starting:          # already serving: show it again
            webbrowser.open(url)
            return
        try:
            server.start()
        except OSError:                 # another process owns the port
            self.status_lbl.config(text=self._("web_failed"), foreground=ERR)
            return
        self._web_starting = True
        webbrowser.open(url)

    def _open_settings(self):
        cfg = load()
        lang = self.lang
        win = tk.Toplevel(self.root)
        win.title(T(lang, "set_title"))
        win.geometry("640x780")
        win.minsize(580, 600)
        win.transient(self.root)
        win.grab_set()
        apply_dark_theme(win)

        def deliver(callback):
            self.q.put({"event": "ui_callback", "window": win, "callback": callback})

        # Scrollable container for settings
        container = ttk.Frame(win)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, highlightthickness=0, background=BG)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frm = ttk.Frame(canvas, padding=(20, 14))

        win_id = canvas.create_window((0, 0), window=frm, anchor="nw")

        def _conf_canvas(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _resize_canvas(e):
            canvas.itemconfigure(win_id, width=e.width)

        frm.bind("<Configure>", _conf_canvas)
        canvas.bind("<Configure>", _resize_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))

        frm.columnconfigure(1, weight=1)
        r = 0

        # Section 1: Fournisseur & Clés API
        sec1 = ttk.LabelFrame(frm, text=" 🔑 Fournisseur IA & Clés API ", padding=12)
        sec1.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        sec1.columnconfigure(1, weight=1)
        sr = 0

        ttk.Label(sec1, text=T(lang, "provider"), font=("Segoe UI", 9, "bold")).grid(
            row=sr, column=0, sticky="w", pady=4)
        provider_cb = ttk.Combobox(sec1, state="readonly", width=30,
                                   values=[PROVIDER_LABELS[p] for p in PROVIDERS])
        provider_cb.current(PROVIDERS.index(cfg["provider"]))
        provider_cb.grid(row=sr, column=1, sticky="ew", pady=4)
        sr += 1

        key_entries = {}
        key_pills = {}
        for p in PROVIDERS:
            p_keys = get_provider_keys(p)
            has_key = len(p_keys) > 0
            ttk.Label(sec1, text=f"{PROVIDER_LABELS[p]} :").grid(
                row=sr, column=0, sticky="w", pady=2)

            cell = ttk.Frame(sec1)
            cell.grid(row=sr, column=1, sticky="ew", pady=2)
            cell.columnconfigure(0, weight=1)

            e = ttk.Entry(cell, show="•")
            stored_val = cfg["api_keys"].get(p, "")
            e.insert(0, stored_val)
            e.grid(row=0, column=0, sticky="ew")
            key_entries[p] = e

            pill = ttk.Label(cell, text="✓" if has_key else "—",
                             foreground=OK if has_key else MUT,
                             font=("Segoe UI", 9, "bold"), width=3)
            pill.grid(row=0, column=1, padx=(6, 0))
            key_pills[p] = pill
            sr += 1

        ttk.Label(sec1, text=T(lang, "keys_hint"), foreground=MUT_LIGHT,
                  wraplength=520, justify="left", font=("Segoe UI", 8)).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=(4, 2))
        sr += 1
        ttk.Label(sec1, text=T(lang, "get_key"), foreground=ACC,
                  font=("Segoe UI", 8)).grid(row=sr, column=0, columnspan=2, sticky="w")
        r += 1

        # Section 2: Modèle & Performances
        local_box = ttk.LabelFrame(frm, text=" IA locale · Ollama / LM Studio ", padding=12)
        local_box.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        local_box.columnconfigure(1, weight=1)
        url_entries = {}
        for n, p in enumerate(LOCAL_PROVIDERS):
            ttk.Label(local_box, text=PROVIDER_LABELS[p]).grid(row=n, column=0, sticky="w", padx=(0, 10))
            entry = ttk.Entry(local_box)
            entry.insert(0, cfg["local_urls"][p])
            entry.grid(row=n, column=1, sticky="ew", pady=3)
            url_entries[p] = entry
        ttk.Label(local_box, text="Démarre le serveur, choisis le fournisseur puis « Charger modèles ».\nUn modèle avec vision est nécessaire pour les captures. Clé facultative.\nUne session locale ne bascule jamais vers un fournisseur cloud.",
                  foreground=MUT, wraplength=520).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        r += 1
        sec2 = ttk.LabelFrame(frm, text=" 🧠 Modèle & Performances ", padding=12)
        sec2.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        sec2.columnconfigure(1, weight=1)
        sr = 0

        ttk.Label(sec2, text=T(lang, "model")).grid(row=sr, column=0, sticky="w", pady=3)
        model_cell = ttk.Frame(sec2)
        model_cell.grid(row=sr, column=1, sticky="ew", pady=3)
        model_cell.columnconfigure(0, weight=1)
        model_cb = ttk.Combobox(model_cell, width=32)
        model_cb.grid(row=0, column=0, sticky="ew")
        load_btn = ttk.Button(model_cell, text=T(lang, "load_models"), style="TButton", width=18)
        load_btn.grid(row=0, column=1, padx=(6, 0))
        sr += 1

        models_lbl = ttk.Label(sec2, text=T(lang, "models_hint"), foreground=MUT, font=("Segoe UI", 8))
        models_lbl.grid(row=sr, column=0, columnspan=2, sticky="w", pady=(0, 6))
        sr += 1

        cache = dict(cfg.get("models_available", {}))
        model_drafts = dict(cfg["models"])
        selected_provider = cfg["provider"]

        def sync_model_picker(_e=None):
            nonlocal selected_provider
            if _e is not None:
                model_drafts[selected_provider] = model_cb.get().strip()
            p = PROVIDERS[provider_cb.current()]
            selected_provider = p
            values = cache.get(p) or []
            model_cb.config(values=values)
            model_cb.delete(0, "end")
            model_cb.insert(0, model_drafts.get(p, ""))

        def do_load_models():
            p = PROVIDERS[provider_cb.current()]
            try:
                save({"api_keys": {k: e.get().strip() for k, e in key_entries.items()},
                      "local_urls": {p: e.get() for p, e in url_entries.items()}})
            except (OSError, ValueError) as e:
                models_lbl.config(text=str(e), foreground=ERR)
                return
            load_btn.config(state="disabled")
            models_lbl.config(text=T(lang, "testing"), foreground=MUT)

            def worker():
                models = list_models(p)
                deliver(lambda: _models_done(p, models))

            def _models_done(p, models):
                if not _alive(win):    # the user closed Settings while we were loading
                    return
                load_btn.config(state="normal")
                if models:
                    cache[p] = models
                    if PROVIDERS[provider_cb.current()] == p:
                        model_cb.config(values=models)
                        if model_cb.get() not in models:
                            model_cb.current(0)
                    models_lbl.config(
                        text=T(lang, "models_loaded", n=len(models)), foreground=OK)
                else:
                    models_lbl.config(text=T(lang, "models_fail"), foreground=ERR)

            threading.Thread(target=worker, daemon=True).start()

        load_btn.config(command=do_load_models)
        provider_cb.bind("<<ComboboxSelected>>", sync_model_picker)
        sync_model_picker()

        ttk.Label(sec2, text=T(lang, "image_width")).grid(row=sr, column=0, sticky="w", pady=3)
        width_cb = ttk.Combobox(sec2, state="readonly", width=10, values=tuple(S["img_widths"]))
        width_cb.set(str(cfg.get("image_width", 1280)))
        width_cb.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1

        ttk.Label(sec2, text=T(lang, "max_steps")).grid(row=sr, column=0, sticky="w", pady=3)
        steps_spin = ttk.Spinbox(sec2, from_=1, to=40, width=8)
        steps_spin.set(cfg.get("max_steps", 20))
        steps_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1

        ttk.Label(sec2, text=T(lang, "step_delay")).grid(row=sr, column=0, sticky="w", pady=3)
        delay_spin = ttk.Spinbox(sec2, from_=0.0, to=6.0, increment=0.2, width=8)
        delay_spin.set(cfg.get("step_delay", 0.4))
        delay_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1

        grid_var = tk.BooleanVar(value=bool(cfg.get("grid", True)))
        ttk.Checkbutton(sec2, text=T(lang, "grid"), variable=grid_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1

        free_var = tk.BooleanVar(value=bool(cfg.get("free_mouse", True)))
        ttk.Checkbutton(sec2, text=T(lang, "free_mouse"), variable=free_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1

        shots_var = tk.BooleanVar(value=bool(cfg.get("screenshot_each_action")))
        ttk.Checkbutton(sec2, text=T(lang, "shots_each"), variable=shots_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1
        chat_eco_var = tk.BooleanVar(value=bool(cfg.get("chat_eco", True)))
        ttk.Checkbutton(sec2, text="Mode éco du Chat (contexte et réponses plus courts)",
                        variable=chat_eco_var).grid(row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1
        ttk.Label(sec2, text="Messages précédents envoyés").grid(row=sr, column=0, sticky="w", pady=3)
        chat_context_spin = ttk.Spinbox(sec2, from_=0, to=20, width=8)
        chat_context_spin.set(cfg.get("chat_context_messages", 6))
        chat_context_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1
        ttk.Label(sec2, text="Longueur max de réponse (tokens)").grid(row=sr, column=0, sticky="w", pady=3)
        chat_tokens_spin = ttk.Spinbox(sec2, from_=128, to=4096, increment=128, width=8)
        chat_tokens_spin.set(cfg.get("chat_response_tokens", 700))
        chat_tokens_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1
        autonomous_var = tk.BooleanVar(value=bool(cfg.get("autonomous_mode", False)))
        ttk.Checkbutton(sec2, text="Mode autonome borné", variable=autonomous_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=(8, 2))
        sr += 1
        ttk.Label(sec2, text="Durée autonome maximale (minutes)").grid(row=sr, column=0, sticky="w", pady=3)
        autonomous_minutes_spin = ttk.Spinbox(sec2, from_=5, to=240, width=8)
        autonomous_minutes_spin.set(cfg.get("autonomous_minutes", 60))
        autonomous_minutes_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1
        ttk.Label(sec2, text="Budget maximal d’appels IA").grid(row=sr, column=0, sticky="w", pady=3)
        autonomous_calls_spin = ttk.Spinbox(sec2, from_=2, to=80, width=8)
        autonomous_calls_spin.set(cfg.get("autonomous_max_calls", 20))
        autonomous_calls_spin.grid(row=sr, column=1, sticky="w", pady=3)
        sr += 1
        ttk.Label(sec2, text="Intervalle minimal entre appels (secondes)").grid(row=sr, column=0, sticky="w", pady=3)
        autonomous_interval_spin = ttk.Spinbox(sec2, from_=15, to=300, increment=15, width=8)
        autonomous_interval_spin.set(cfg.get("autonomous_min_interval", 30))
        autonomous_interval_spin.grid(row=sr, column=1, sticky="w", pady=3)
        r += 1

        # Section 3: Mode Jeu & Fenêtre
        sec3 = ttk.LabelFrame(frm, text=" 🎮 Mode Jeu & Capture Fenêtre ", padding=12)
        sec3.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        sec3.columnconfigure(1, weight=1)
        sr = 0

        game_var = tk.BooleanVar(value=bool(cfg.get("game_mode")))
        ttk.Checkbutton(sec3, text=T(lang, "game_mode"), variable=game_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1

        win_var = tk.BooleanVar(value=bool(cfg.get("window_mode")))
        ttk.Checkbutton(sec3, text=T(lang, "window_only"), variable=win_var).grid(
            row=sr, column=0, columnspan=2, sticky="w", pady=2)
        sr += 1

        ttk.Label(sec3, text=T(lang, "set_window_title")).grid(row=sr, column=0, sticky="w", pady=3)
        win_title_entry = ttk.Entry(sec3)
        win_title_entry.insert(0, cfg.get("window_title", ""))
        win_title_entry.grid(row=sr, column=1, sticky="ew", pady=3)
        r += 1

        # Section 4: Langue & Système
        sec4 = ttk.LabelFrame(frm, text=" 🌐 Langue de l'application ", padding=12)
        sec4.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        sec4.columnconfigure(1, weight=1)

        ttk.Label(sec4, text=T(lang, "language")).grid(row=0, column=0, sticky="w", pady=3)
        lang_cb = ttk.Combobox(sec4, state="readonly", width=14, values=["Français", "English"])
        lang_cb.current(0 if cfg.get("language", "fr") == "fr" else 1)
        lang_cb.grid(row=0, column=1, sticky="w", pady=3)
        r += 1

        def collect_and_save():
            p = PROVIDERS[provider_cb.current()]
            model_drafts[p] = model_cb.get().strip()
            try:
                delay = max(0.0, float(delay_spin.get()))
            except ValueError:
                delay = 0.4
            try:
                max_steps = max(1, min(40, int(steps_spin.get())))
            except ValueError:
                max_steps = 20
            new_lang = "fr" if lang_cb.current() == 0 else "en"
            return save({
                "provider": p,
                "local_urls": {p: e.get() for p, e in url_entries.items()},
                "api_keys": {k: e.get() for k, e in key_entries.items()},
                "models": model_drafts,
                "models_available": cache,
                "max_steps": max_steps,
                "grid": bool(grid_var.get()),
                "image_width": int(width_cb.get() or 0),
                "game_mode": bool(game_var.get()),
                "window_mode": bool(win_var.get()),
                "window_title": win_title_entry.get().strip(),
                "step_delay": delay,
                "screenshot_each_action": bool(shots_var.get()),
                "free_mouse": bool(free_var.get()),
                "chat_eco": bool(chat_eco_var.get()),
                "chat_context_messages": chat_context_spin.get(),
                "chat_response_tokens": chat_tokens_spin.get(),
                "autonomous_mode": bool(autonomous_var.get()),
                "autonomous_minutes": autonomous_minutes_spin.get(),
                "autonomous_max_calls": autonomous_calls_spin.get(),
                "autonomous_min_interval": autonomous_interval_spin.get(),
                "language": new_lang,
            })

        test_lbl = ttk.Label(frm, text="", wraplength=540, justify="left")
        info_lbl = ttk.Label(frm, text="", foreground=MUT, wraplength=540, justify="left")

        def do_save():
            try:
                new_cfg = collect_and_save()
            except (OSError, ValueError) as e:
                info_lbl.config(text=str(e), foreground=ERR)
                return
            old_lang = cfg.get("language", "fr")
            self._refresh_badge()
            self.game_var.set(new_cfg["game_mode"])
            self.win_var.set(new_cfg["window_mode"])
            self.win_selected = new_cfg["window_title"]
            self._refresh_windows()
            if new_cfg.get("language") != old_lang:
                info_lbl.config(text=T(new_cfg.get("language", "fr"), "saved_restart"))
                self.restart_requested = True
                owned = agent.active_run()
                if owned is not None:
                    owned.stop()

                def restart_when_idle():
                    if agent.active_run() is not None:
                        self.root.after(100, restart_when_idle)
                    else:
                        self.root.destroy()

                win.after(500, restart_when_idle)
            else:
                info_lbl.config(text=T(self.lang, "saved"), foreground=OK)

        def do_test():
            try:
                tested_cfg = collect_and_save()
            except (OSError, ValueError) as e:
                test_lbl.config(text=str(e), foreground=ERR)
                return
            p = tested_cfg["provider"]
            self._refresh_badge()
            test_lbl.config(text=T(self.lang, "testing"), foreground=MUT)

            def worker():
                t0 = time.time()
                try:
                    reply, used_p = chat_with_fallback(p, "Reply with exactly: OK", allow_fallback=False)
                    ms = int((time.time() - t0) * 1000)
                    model_used = load().get("models", {}).get(used_p, "")
                    deliver(lambda: test_lbl.config(
                        text=T(self.lang, "test_ok", ms=ms, model=f"{PROVIDER_LABELS.get(used_p, used_p)} ({model_used})", reply=reply[:60]),
                        foreground=OK,
                    ))
                except Exception as e:
                    error = str(e)
                    deliver(lambda error=error: test_lbl.config(text=f"✖ {error}", foreground=ERR))

            threading.Thread(target=worker, daemon=True).start()

        # Action Buttons
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        r += 1
        ttk.Button(btns, text=T(lang, "save"), style="Accent.TButton",
                   command=do_save).pack(side="left")
        ttk.Button(btns, text=T(lang, "test"), style="TButton",
                   command=do_test).pack(side="left", padx=8)
        ttk.Button(btns, text=T(lang, "close"), style="TButton",
                   command=win.destroy).pack(side="right")

        test_lbl.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        r += 1
        info_lbl.grid(row=r, column=0, columnspan=2, sticky="ew")
        r += 1
        ttk.Label(frm, foreground="#525d70", wraplength=540, justify="left",
                  text=T(lang, "footer"), font=("Segoe UI", 8)).grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # ------------------------------------------------------------ misc
    def _show_screen_info(self):
        info = display.screen_info()
        p, v = info.get("primary", {}), info.get("virtual", {})
        messagebox.showinfo(
            T(self.lang, "screen_info"),
            T(self.lang, "info_body",
              w=p.get("width_px", "?"), h=p.get("height_px", "?"),
              dpi=p.get("dpi", "?"), scale=p.get("scale_percent", 100),
              vw=v.get("width_px", "?"), vh=v.get("height_px", "?"),
              sys=info.get("system", "?")),
        )

    def _on_close(self):
        self._persist_chat()
        owned = agent.active_run() or self.run
        if owned:
            if not owned.stopped and not messagebox.askyesno(T(self.lang, "app"), T(self.lang, "still_running")):
                return
            owned.stop()
            # The run thread dies with the process, so its own finally may never
            # run: free what it is holding now, or the user is left with a stuck
            # key / mouse button on their desktop.
            if getattr(owned, "execution_mode", "desktop") != "browser":
                try:
                    input_control.release_all_keys()
                    input_control.mouse_up("left")
                    input_control.mouse_up("right")
                except Exception:  # noqa: BLE001 - closing must never fail
                    pass
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except Exception:
                pass
            self._ghost = None
        self.root.destroy()


def _alive(widget) -> bool:
    """True while a window still exists: a worker's result must never be
    delivered into the Settings dialog the user has already closed."""
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _icon_path():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "app.ico")
        if os.path.exists(p):
            return p
    for cand in (os.path.join(app_root(), "assets", "app.ico"), "app.ico"):
        if os.path.exists(cand):
            return cand
    return None


def main():
    load_dotenv_if_present()
    migrate_legacy_keys()      # explicit, once: reading a config never writes one
    if getattr(sys, "frozen", False):
        os.chdir(app_root())
    while True:
        root = tk.Tk()
        app = App(root)
        root.mainloop()
        if app.restart_requested:
            continue
        break

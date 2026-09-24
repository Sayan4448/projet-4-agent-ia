"""Local web UI: chat with the agent, run goals, configure providers in Settings.

Served at http://127.0.0.1:8765 (localhost only — nothing is exposed to the network).
"""
import base64
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, display
from .agent import RunBusy, run_goal
from .ai_client import AIError, chat
from .paths import load_dotenv_if_present
from .settings import PROVIDERS, SPEEDS, get_provider_keys, load, migrate_legacy_keys, save

HOST = "127.0.0.1"
PORT = 8765


# --------------------------------------------------------------------- pages
def _page(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Agent Screen</title>
<style>
 :root {{ --bg:#0f1115; --card:#171a21; --line:#242936; --txt:#e8eaf0; --mut:#8b93a7; --acc:#6c8cff; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; font:15px/1.5 "Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--txt); }}
 header {{ display:flex; align-items:center; gap:16px; padding:14px 22px; border-bottom:1px solid var(--line); }}
 header h1 {{ font-size:17px; margin:0; }}
 nav a {{ color:var(--mut); text-decoration:none; margin-right:14px; padding:4px 2px; }}
 nav a.active, nav a:hover {{ color:var(--txt); }}
 main {{ max-width:900px; margin:24px auto; padding:0 16px; }}
 .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; margin-bottom:18px; }}
 h2 {{ font-size:15px; margin:0 0 12px; }}
 .mut {{ color:var(--mut); font-size:13px; }}
 button {{ background:var(--acc); color:#fff; border:0; border-radius:8px; padding:9px 16px; font-size:14px; cursor:pointer; }}
 button:disabled {{ opacity:.5; cursor:default; }}
 button.ghost {{ background:transparent; border:1px solid var(--line); color:var(--txt); }}
 input, select, textarea {{ background:#0d0f14; border:1px solid var(--line); color:var(--txt);
   border-radius:8px; padding:9px 11px; font-size:14px; width:100%; }}
 label {{ display:block; margin:12px 0 5px; font-size:13px; color:var(--mut); }}
 .row {{ display:flex; gap:12px; }} .row > div {{ flex:1; }}
 #chat {{ height:340px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; margin-bottom:12px; }}
 .msg {{ max-width:80%; padding:9px 13px; border-radius:12px; white-space:pre-wrap; }}
 .msg.user {{ align-self:flex-end; background:var(--acc); color:#fff; }}
 .msg.bot {{ align-self:flex-start; background:#1d2230; }}
 .step {{ background:#10131a; border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin:6px 0; font-size:13px; }}
 .ok {{ color:#7bd88f; }} .err {{ color:#ff7b72; }}
 .kv {{ display:grid; grid-template-columns:auto 1fr; gap:4px 18px; font-size:14px; }}
 .kv b {{ color:var(--mut); font-weight:600; }}
 img.shot {{ max-width:100%; border-radius:8px; border:1px solid var(--line); }}
</style>{extra_head}</head><body>
<script>
// shared by every page: page scripts run after this, so they can use $ directly
const $ = id => document.getElementById(id);
async function jget(u){{ const r = await fetch(u); return r.json(); }}
async function jpost(u, body){{ const r = await fetch(u, {{method:'POST',
  headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body)}}); return r.json(); }}
</script>
<header>
  <h1>🤖 Agent Screen <span class="mut">v{__version__}</span></h1>
  <nav>
    <a href="/" id="nav-home">Chat</a>
    <a href="/settings" id="nav-settings">Settings</a>
    <a href="/screen" id="nav-screen">Screen</a>
  </nav>
  <span style="margin-left:auto" class="mut" id="provider-badge"></span>
</header><main>{body}</main></body></html>"""


def _home_page() -> str:
    return _page("Chat", """
<div class="card">
  <h2>Goal runner</h2>
  <p class="mut">Describe a goal — the agent takes a screenshot, decides actions
  (mouse, keyboard), executes them and re-checks the screen after each step.</p>
  <div class="row">
    <input id="goal" placeholder="e.g. Open Notepad and type hello world">
    <button id="run">Run goal</button>
  </div>
  <div id="steps" style="margin-top:12px"></div>
</div>
<div class="card">
  <h2>Chat</h2>
  <div id="chat"></div>
  <div class="row">
    <input id="chatin" placeholder="Ask something (current provider sees your screen if you attach it)">
    <button class="ghost" id="snap" title="Attach a fresh screenshot">📸 + Send</button>
    <button id="send">Send</button>
  </div>
</div>
<script>
jget('/api/status').then(s => {
  $('provider-badge').textContent = 'Provider: ' + s.provider + ' · ' + s.model +
    (s.has_key ? ' ✅' : ' ⚠️ no API key');
});

$('run').onclick = async () => {
  const goal = $('goal').value.trim(); if (!goal) return;
  $('run').disabled = true; $('steps').innerHTML = '<span class="mut">Running…</span>';
  const res = await jpost('/api/run', {goal});
  if (res.error) {
    $('steps').innerHTML = '<span class="err">' + res.error + '</span>';
    $('run').disabled = false;
    return;
  }
  let html = '';
  // a step is {step, thought, summary, done, actions[]} where `summary` holds the
  // actions that ran (or the model's closing summary on the last step) and
  // `actions` only lists the ones that FAILED.
  for (const st of (res.steps || [])) {
    let failed = '';
    for (const a of (st.actions || [])) {
      failed += '<div class="err">✖ ' + a.name + '(' + JSON.stringify(a.args || {}) +
                ') : ' + (a.error || 'failed') + '</div>';
    }
    html += '<div class="step"><b>Step ' + st.step + '</b> ' +
      (st.done
        ? '<span class="ok">✔ done — ' + (st.summary || '') + '</span>'
        : (st.summary ? '→ <code>' + st.summary + '</code>' : '')) +
      failed +
      (st.thought ? '<div class="mut">' + st.thought + '</div>' : '') + '</div>';
  }
  $('steps').innerHTML = html || '<span class="err">No steps.</span>';
  $('run').disabled = false;
};

async function sendChat(withShot) {
  const text = $('chatin').value.trim(); if (!text) return;
  addMsg('user', text); $('chatin').value = '';
  const body = {message: text, screenshot: withShot};
  const res = await jpost('/api/chat', body);
  addMsg('bot', res.reply || ('⚠️ ' + (res.error || 'error')));
}
$('send').onclick = () => sendChat(false);
$('snap').onclick = () => sendChat(true);
$('chatin').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(false); });

function addMsg(who, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + who; d.textContent = text;
  $('chat').appendChild(d); $('chat').scrollTop = $('chat').scrollHeight;
}
</script>""")


def _settings_page() -> str:
    return _page("Settings", """
<div class="card">
  <h2>Provider & API keys</h2>
  <p class="mut">Keys are stored locally in <code>data/config.json</code> — nothing is sent anywhere
  except to the provider you choose.</p>
  <label>Default provider</label>
  <select id="provider"></select>
  <div id="keys"></div>
  <label>Max steps per goal</label>
  <input id="max_steps" type="number" min="1" max="40">
  <div style="margin-top:16px"><button id="save">Save settings</button>
  <span id="saved" class="ok" style="margin-left:10px"></span></div>
</div>
<div class="card">
  <h2>Models (optional overrides)</h2>
  <div id="models"></div>
</div>
<script>
const PROVIDERS = ['gemini','openai','anthropic','groq','deepseek','openrouter'];
const LABELS = {gemini:'Google Gemini', openai:'OpenAI', anthropic:'Anthropic (Claude)',
  groq:'Groq', deepseek:'DeepSeek', openrouter:'OpenRouter'};
const ENVHINT = {gemini:'GEMINI_API_KEY', openai:'OPENAI_API_KEY', anthropic:'ANTHROPIC_API_KEY',
  groq:'GROQ_API_KEY', deepseek:'DEEPSEEK_API_KEY', openrouter:'OPENROUTER_API_KEY'};
let cfg;

async function loadCfg(){
  cfg = await (await fetch('/api/settings')).json();
  const sel = $('provider');
  for (const p of PROVIDERS) {
    const o = document.createElement('option'); o.value = p; o.textContent = LABELS[p]; sel.appendChild(o);
  }
  sel.value = cfg.provider;
  sel.onchange = renderKeys;
  const mk = $('models');
  for (const p of PROVIDERS) {
    const l = document.createElement('label'); l.textContent = LABELS[p] + ' model';
    const i = document.createElement('input'); i.id = 'model-' + p; i.value = cfg.models[p] || '';
    mk.appendChild(l); mk.appendChild(i);
  }
  $('max_steps').value = cfg.max_steps;
  renderKeys();
}
function renderKeys(){
  const wrap = $('keys'); wrap.innerHTML = '';
  for (const p of PROVIDERS) {
    const has = (cfg.api_keys[p] || '').length > 0;
    const env = cfg.env_keys && cfg.env_keys[p];
    const l = document.createElement('label');
    l.textContent = LABELS[p] + ' API key' + (has ? ' ✅ saved' : '') +
      (env ? ' (found in .env: ' + env + ')' : '');
    const i = document.createElement('input');
    i.id = 'key-' + p; i.type = 'password'; i.placeholder = 'Paste your ' + LABELS[p] + ' key…';
    i.value = cfg.api_keys[p] || '';
    wrap.appendChild(l); wrap.appendChild(i);
  }
}
$('save').onclick = async () => {
  const api_keys = {}, models = {};
  for (const p of PROVIDERS) { api_keys[p] = $('key-' + p).value; models[p] = $('model-' + p).value; }
  const res = await (await fetch('/api/settings', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({provider: $('provider').value, api_keys, models,
      max_steps: parseInt($('max_steps').value || '8')})})).json();
  cfg = res; renderKeys();
  $('saved').textContent = 'Saved ✓'; setTimeout(() => $('saved').textContent = '', 2500);
};
loadCfg();
</script>""")


def _screen_page() -> str:
    return _page("Screen", """
<div class="card">
  <h2>Screen information</h2>
  <div id="info" class="kv"><span class="mut">Loading…</span></div>
  <div style="margin-top:14px"><button id="refresh">Refresh</button></div>
</div>
<div class="card">
  <h2>Current screenshot</h2>
  <div id="shotwrap"><span class="mut">Click “Take screenshot”.</span></div>
  <div style="margin-top:12px"><button id="shot">Take screenshot</button></div>
</div>
<script>
async function loadInfo(){
  const s = await (await fetch('/api/screen')).json();
  let html = '';
  const p = s.primary || {}, v = s.virtual || {};
  html += '<b>Primary screen</b><span>' + (p.width_px||'?') + ' × ' + (p.height_px||'?') + ' physical pixels</span>';
  html += '<b>DPI / scaling</b><span>' + (p.dpi||'?') + ' DPI (' + (p.scale_percent||100) + '%)</span>';
  html += '<b>All monitors</b><span>' + (v.width_px||'?') + ' × ' + (v.height_px||'?') + ' pixels (virtual desktop)</span>';
  html += '<b>System</b><span>' + (s.system||'?') + '</span>';
  $('info').innerHTML = html;
}
$('refresh').onclick = loadInfo; loadInfo();
$('shot').onclick = async () => {
  $('shotwrap').innerHTML = '<span class="mut">Capturing…</span>';
  const r = await (await fetch('/api/screenshot')).json();
  $('shotwrap').innerHTML = r.image ? '<img class="shot" src="data:image/png;base64,' + r.image + '">'
                                   : '<span class="err">' + (r.error||'error') + '</span>';
};
</script>""")


# -------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8"):
        data = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:  # the tab was reloaded/closed: no client left to tell
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > 5_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    # ---- GET
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, _home_page())
        elif path == "/settings":
            self._send(200, _settings_page())
        elif path == "/screen":
            self._send(200, _screen_page())
        elif path == "/api/status":
            cfg = load()
            key = cfg["api_keys"].get(cfg["provider"], "")
            self._json({"provider": cfg["provider"], "model": cfg["models"].get(cfg["provider"], ""),
                        "has_key": bool(key)})
        elif path == "/api/settings":
            cfg = load()
            from .settings import ENV_KEYS
            env_found = {}
            import os
            for p in PROVIDERS:
                for env_name in ENV_KEYS.get(p, []):
                    if os.environ.get(env_name):
                        env_found[p] = env_name
                        break
            safe = dict(cfg)
            safe["api_keys"] = {p: bool(get_provider_keys(p)) for p in PROVIDERS}
            self._json({**safe, "env_keys": env_found})
        elif path == "/api/screen":
            self._json(display.screen_info())
        elif path == "/api/screenshot":
            try:
                self._json({"image": display.take_screenshot()})
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)
        else:
            self._send(404, "<h1>404</h1>")

    # ---- POST
    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_json()
        if path == "/api/settings":
            self._json(save(body))
        elif path == "/api/run":
            goal = str(body.get("goal", "")).strip()
            if not goal:
                self._json({"error": "Empty goal."}, 400)
                return
            cfg = load()
            try:
                self._json(run_goal(goal, cfg["provider"], max_steps=cfg["max_steps"],
                                    execution_mode=cfg["execution_mode"], eco_mode=cfg["eco_mode"],
                                    limit_actions_per_capture=cfg["limit_actions_per_capture"],
                                    actions_per_capture=cfg["actions_per_capture"],
                                    grid=cfg["grid"], image_width=cfg["image_width"],
                                    jpeg_quality=cfg["jpeg_quality"], game_mode=cfg["game_mode"],
                                    window_mode=cfg["window_mode"], window_title=cfg["window_title"],
                                    free_mouse=cfg["free_mouse"], virtual_cursor=cfg["virtual_cursor"],
                                    agent_profile=cfg["agent_profile"], autonomous_mode=cfg["autonomous_mode"],
                                    autonomous_minutes=cfg["autonomous_minutes"],
                                    autonomous_max_calls=cfg["autonomous_max_calls"],
                                    autonomous_min_interval=cfg["autonomous_min_interval"],
                                    virtual_input=cfg["virtual_input"], memory_enabled=cfg["memory_enabled"],
                                    virtual_fallback=cfg.get("virtual_fallback", True),
                                    type_settle=SPEEDS.get(cfg.get("speed", "normal"),
                                                           SPEEDS["normal"])["settle"]))
            except RunBusy:
                # a run is already in flight, here or in the desktop window: one
                # owner (agent) decides, so a second tab cannot share the mouse
                self._json({"error": "A run is already in progress.", "steps": []}, 409)
            except AIError as e:
                self._json({"error": str(e), "steps": []}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"{type(e).__name__}: {e}", "steps": []}, 500)
        elif path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                self._json({"error": "Empty message."}, 400)
                return
            cfg = load()
            b64 = None
            if body.get("screenshot"):
                try:
                    b64 = display.take_screenshot()
                except Exception:  # noqa: BLE001
                    b64 = None
            try:
                reply = chat(cfg["provider"], message,
                             system="You are Agent Screen, a helpful desktop assistant on Windows.",
                             b64_png=b64)
                self._json({"reply": reply})
            except AIError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        else:
            self._send(404, "<h1>404</h1>")


def start() -> ThreadingHTTPServer:
    """Bind the local page and serve it on a daemon thread.

    Used by the desktop app's 🌐 button and by main(). Binding happens here, so a
    caller can open the browser right after the call and always find the page
    live. Raises OSError if the port is already taken.
    """
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    load_dotenv_if_present()
    migrate_legacy_keys()      # explicit, once: reading a config never writes one
    cfg = load()
    url = f"http://{HOST}:{PORT}"
    print(f"Agent Screen v{__version__}")
    print(f"  Provider : {cfg['provider']} ({cfg['models'].get(cfg['provider'])})")
    print(f"  API key  : {'configured' if cfg['api_keys'].get(cfg['provider']) else 'NOT SET — open Settings'}")
    print(f"  UI       : {url}  (Ctrl+C to quit)")
    start()
    if not os.environ.get("AGENT_SCREEN_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()

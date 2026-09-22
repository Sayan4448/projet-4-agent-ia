"""Browser-only execution: Playwright page input, never desktop input.

Runs in the AgentRun worker thread. Uses installed Edge/Chrome, with a dedicated
profile; browser binaries are not downloaded at runtime. No desktop actions are
exposed and only http(s)/about:blank navigation is permitted.
"""
import base64
import io
from urllib.parse import quote, urlsplit

from PIL import Image
from .paths import data_dir
from .display import _draw_grid

ALLOWED = {"open_url", "search_web", "mouse_move", "mouse_click", "mouse_double_click",
           "mouse_scroll", "mouse_hscroll", "type_text", "press_key", "hotkey", "wait",
           "observe_motion"}
KEYS = {"enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape", "escape": "Escape",
        "backspace": "Backspace", "delete": "Delete", "space": "Space", "up": "ArrowUp",
        "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "home": "Home",
        "end": "End", "pageup": "PageUp", "pagedown": "PageDown"}
SHORTCUTS = {("ctrl", "a"): "Control+a", ("ctrl", "c"): "Control+c",
             ("ctrl", "v"): "Control+v", ("ctrl", "f"): "Control+f",
             ("ctrl", "z"): "Control+z", ("ctrl", "y"): "Control+y",
             ("shift", "tab"): "Shift+Tab"}


class BrowserSession:
    def __init__(self):
        self.engine = self.context = self.page = None
        self.scale = 1.0
        self.origin = (0, 0)
        self.size = (1280, 800)

    def start(self):
        from playwright.sync_api import sync_playwright
        self.engine = sync_playwright().start()
        errors = []
        for channel in ("msedge", "chrome"):
            try:
                self.context = self.engine.chromium.launch_persistent_context(
                    str(data_dir() / "browser-profile"), channel=channel, headless=False,
                    viewport={"width": 1280, "height": 800}, accept_downloads=False,
                    args=["--disable-features=ExternalProtocolDialog"])
                break
            except Exception as e:
                errors.append(str(e).splitlines()[0])
        if self.context is None:
            self.close()
            raise RuntimeError("Mode navigateur : installe Microsoft Edge ou Google Chrome. " + " / ".join(errors))
        self.context.set_default_timeout(12000)
        self.context.set_default_navigation_timeout(20000)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto("about:blank")
        self.page.set_content("<html><body style='background:#10101a;color:#eee;font:24px system-ui;padding:80px'>"
                              "<h1>Projet 4 · Agent IA</h1><p>Session navigateur prête.</p>"
                              "<p style='color:#aaa'>Les actions de l’agent restent dans cette session.</p></body></html>")

    def _active_page(self):
        pages = [p for p in self.context.pages if not p.is_closed()]
        if not pages:
            raise RuntimeError("La fenêtre du navigateur a été fermée.")
        self.page = pages[-1]
        url = self.page.url
        if url != "about:blank" and urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("Navigation hors http(s) non autorisée en mode navigateur.")
        return self.page

    def screenshot(self, width=1280, quality=80, grid=True):
        page = self._active_page()
        raw = page.screenshot(type="png", animations="disabled")
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        self.size = image.size
        pos = page.evaluate("({x:screenX+(outerWidth-innerWidth)/2,y:screenY+outerHeight-innerHeight})")
        self.origin = (int(pos["x"]), int(pos["y"]))
        if width and image.width > width:
            image.thumbnail((width, 10000))
        self.scale = self.size[0] / image.width
        if grid:
            image = _draw_grid(image, image.width, image.height, 1)
        out = io.BytesIO()
        image.save(out, format="JPEG" if quality else "PNG", **({"quality": quality} if quality else {}))
        return base64.b64encode(out.getvalue()).decode("ascii")

    def point(self, args):
        if args.get("x") is None or args.get("y") is None:
            raise ValueError("Le mode navigateur exige x et y pour chaque action de souris.")
        x, y = float(args["x"]) * self.scale, float(args["y"]) * self.scale
        if not (0 <= x < self.size[0] and 0 <= y < self.size[1]):
            raise ValueError("Coordonnées hors de la page du navigateur.")
        return x, y

    def cursor_position(self, args):
        x, y = self.point(args)
        return int(x + self.origin[0]), int(y + self.origin[1])

    def execute(self, name, args):
        if name not in ALLOWED:
            raise ValueError(f"Action interdite en mode navigateur : {name}")
        page = self._active_page()
        if name == "observe_motion":
            raise RuntimeError("observe_motion is handled by the active agent session")
        if name in ("open_url", "search_web"):
            url = str(args.get("url", "")).strip() if name == "open_url" else "https://www.google.com/search?q=" + quote(str(args.get("query", "")))
            if "://" not in url:
                url = "https://" + url
            if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
                raise ValueError("Seules les adresses http(s) sont acceptées.")
            page.goto(url, wait_until="domcontentloaded")
        elif name in ("mouse_move", "mouse_click", "mouse_double_click"):
            x, y = self.point(args)
            if name == "mouse_move":
                page.mouse.move(x, y)
            else:
                button = args.get("button", "left")
                if button not in ("left", "right", "middle"):
                    raise ValueError("Bouton de souris invalide")
                page.mouse.click(x, y, button=button,
                                 click_count=2 if name == "mouse_double_click" else max(1, min(3, int(args.get("clicks", 1)))))
        elif name == "type_text":
            page.keyboard.insert_text(str(args.get("text", ""))[:12000])
        elif name == "press_key":
            key = str(args.get("key", "")).lower()
            mapped = KEYS.get(key)
            if mapped is None and len(key) == 1 and key.isalnum():
                mapped = key
            if not mapped:
                raise ValueError(f"Touche indisponible en mode navigateur : {key}")
            page.keyboard.press(mapped)
        elif name == "hotkey":
            from .agent import _keys
            keys = tuple(k.lower().replace("control", "ctrl") for k in _keys(args))
            if keys not in SHORTCUTS:
                raise ValueError("Raccourci indisponible : utilise open_url/search_web pour naviguer.")
            page.keyboard.press(SHORTCUTS[keys])
        elif name in ("mouse_scroll", "mouse_hscroll"):
            amount = max(-5000, min(5000, int(args.get("amount", 0)) * 100))
            page.mouse.wheel(amount if name == "mouse_hscroll" else 0,
                             -amount if name == "mouse_scroll" else 0)
        return {"ok": True, "url": page.url}

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            if self.engine:
                self.engine.stop()
            self.context = self.engine = self.page = None

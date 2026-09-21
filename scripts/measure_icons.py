"""Measure what the model really identifies among the icons of this screen.

The README claims the agent recognises logos through discriminative features. No
amount of prompt reading settles that: it takes a real capture of this desktop
and a real model answer, compared with what is actually there. This script is
that measurement and nothing else — it looks, it asks, it compares. It never
clicks, never moves the mouse and never starts a run.

    .venv/Scripts/python scripts/measure_icons.py

What it does, in order:
  1. ground truth — the shell's own desktop items and the applications that own
     a window (the model never sees either list);
  2. a test set built from that truth: up to five apps that are really here plus
     one invented name that is certainly nowhere (a control: naming it is a
     hallucination, whatever the coordinate);
  3. one real call, with the app's own SYSTEM_PROMPT, capture and grid settings.

Scoring: a target counts as located when the model names it *and* gives a point
inside the real screen — those two are objective. Whether that point is the
right pixel is printed to be checked by eye; nothing here clicks to find out.

Exit code 2 when the call cannot be made (no key, quota exhausted): the ground
truth still prints, so the measurement replays the moment quota returns.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_screen import agent, ai_client, display, input_control, settings  # noqa: E402

# The apps the user's question is about, when this machine really has them.
WANTED = ["brave", "discord", "steam", "obs", "chrome", "chrom", "firefox", "edge",
          "vscode", "notepad", "terminal", "spotify", "explorer", "vlc", "whatsapp"]
# A name that exists nowhere: the control for "confuses look-alike logos".
FAKE = "Nimbus Chat"

DESKTOP_ITEMS = ("(New-Object -ComObject Shell.Application).NameSpace(0).Items()"
                 " | ForEach-Object { $_.Name }")


def _norm(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def desktop_items() -> list:
    """What is really on the desktop, read from the shell (not from the screen)."""
    res = input_control.run_terminal_command(DESKTOP_ITEMS)
    out = res.get("stdout") or ""
    return [line.strip() for line in out.splitlines() if line.strip()]


def open_apps() -> list:
    """The applications a taskbar would show: the processes that own a window."""
    apps = {}
    for win in display.list_windows():
        exe = display.window_exe(win["hwnd"])
        if exe:
            apps.setdefault(Path(exe).stem.lower(), win["title"])
    return sorted(apps)


def test_set(truth: list, apps: list) -> list:
    """Up to five really-present apps (the interesting ones first) + the control.

    Running applications come first: they are what a taskbar shows, and they have
    the plain names the user means (a desktop shortcut can be called anything).
    """
    picked = []
    for want in WANTED:
        for n in apps + truth:
            if want in _norm(n) and not any(_norm(n) == _norm(p) for p in picked):
                picked.append(n)
                break
        if len(picked) == 5:
            break
    return picked + [FAKE]


def question(targets: list) -> str:
    names = ", ".join(f'"{t}"' for t in targets)
    return (
        "Look at this screenshot. For each of these names, tell me whether its icon is "
        f"visible right now on the desktop or the taskbar: {names}. "
        'Answer with strict JSON: {"icons":[{"name":"...","found":true,"x":0,"y":0}]} '
        "where x,y is the centre of that icon in REAL screen pixels. "
        "Use found=false when you cannot see it — never guess a name you do not see."
    )


def ask_model(cfg: dict, b64: str, targets: list) -> list:
    """One real call, with the prompt and capture settings the agent really uses."""
    reply = ai_client.chat(cfg["provider"], question(targets), system=agent.SYSTEM_PROMPT,
                           b64_png=b64, mime="image/jpeg")
    block = re.search(r"\{.*\}", reply, re.S)
    data = json.loads(block.group(0)) if block else {}
    return [i for i in (data.get("icons") or []) if isinstance(i, dict)]


def main() -> int:
    cfg = settings.load()
    primary = (display.screen_info().get("primary") or {})
    w, h = int(primary.get("width_px") or 0), int(primary.get("height_px") or 0)
    print(f"modele            : {cfg['provider']} / {cfg['models'].get(cfg['provider'])}")
    print(f"ecran             : {w}x{h}")

    truth, apps = desktop_items(), open_apps()
    print(f"verite - bureau   : {len(truth)} elements (dont "
          + ", ".join(n for n in truth if any(x in _norm(n) for x in WANTED))[:220] + ")")
    print(f"verite - fenetres : {', '.join(apps) if apps else '-'}")
    targets = test_set(truth, apps)
    print(f"cibles du test    : {', '.join(targets)}  (le dernier est un contrôle inventé)")

    try:
        b64, scale = display.capture_for_model(
            grid=cfg.get("grid", True), max_width=cfg.get("image_width", 1280),
            jpeg_quality=cfg.get("jpeg_quality", 80))
        print(f"capture           : envoyee au modele, echelle image->reel {scale:g}")
    except Exception as e:  # noqa: BLE001
        print(f"capture impossible : {type(e).__name__}: {e}")
        return 2

    try:
        icons = ask_model(cfg, b64, targets)
    except Exception as e:  # noqa: BLE001
        print(f"appel modele impossible ({type(e).__name__}) : {str(e)[:200]}")
        print("mesure NON faite : relancer quand la cle/le quota est disponible.")
        return 2

    answers = {_norm(i.get("name")): i for i in icons}
    located, hallucinated = [], []
    for target in targets:
        hit = next((a for key, a in answers.items() if key and key in _norm(target)), None)
        shown = target != FAKE
        if not hit or not hit.get("found"):
            print(f"  {target:22} : non vue" + ("" if shown else "  <- contrôle: correct"))
            continue
        x, y = hit.get("x"), hit.get("y")
        inside = isinstance(x, (int, float)) and isinstance(y, (int, float)) \
            and 0 <= x <= w and 0 <= y <= h
        if not shown:
            hallucinated.append(target)
            print(f"  {target:22} : ANNONCEE a ({x},{y})  <- contrôle: invention")
        elif inside:
            located.append(target)
            print(f"  {target:22} : vue a ({x},{y}) — à vérifier à l'oeil")
        else:
            print(f"  {target:22} : vue mais hors écran ({x},{y})")

    real = [t for t in targets if t != FAKE]
    print(f"resultat          : {len(located)}/{len(real)} cibles réelles nommées et placées "
          f"dans l'écran ; contrôle inventé annoncé : {len(hallucinated)}/1")
    print("limite            : la justesse du pixel (la bonne icône à cette position) "
          "n'est prouvée par aucun test automatique — la relire sur la capture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- mode: python ; coding: utf-8 -*-
# Build: .venv/Scripts/python -m PyInstaller AgentScreen.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("agent_screen")

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("assets/app.ico", ".")],
    hiddenimports=hidden + ["tkinter", "pyautogui", "PIL.ImageGrab", "PIL.ImageTk", "pygetwindow", "pymsgbox", "pytweening", "pyscreeze", "pyperclip", "mouseinfo"],
    excludes=["matplotlib", "numpy", "pandas", "scipy", "pytest", "setuptools", "pyinstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgentScreen",
    console=False,            # windowed desktop app
    disable_windowed_traceback=False,
    uac_admin=False,          # ordinary desktop app; Run as administrator only for elevated targets
    upx=False,
    runtime_tmpdir=None,
    icon="assets/app.ico",
)

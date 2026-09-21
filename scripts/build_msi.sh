#!/usr/bin/env bash
# Build everything: icon -> exe (PyInstaller) -> MSI (WiX 3.11)
# Usage: bash scripts/build_msi.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/Scripts/python"
VERSION=$("$PY" -c "from agent_screen import __version__; print(__version__)")

echo "==> [1/4] Icon"
"$PY" scripts/make_icon.py

echo "==> [2/4] Exe (PyInstaller)"
"$PY" -m PyInstaller AgentScreen.spec --noconfirm

echo "==> [3/4] Compile MSI (candle)"
cd installer
../tools/wix311/candle.exe -arch x64 -o AgentScreen.wixobj AgentScreen.wxs

echo "==> [4/4] Link MSI (light)"
../tools/wix311/light.exe -ext WixUIExtension -o "../dist/AgentScreen-$VERSION.msi" AgentScreen.wixobj
rm -f AgentScreen.wixobj AgentScreen.wixpdb "../dist/AgentScreen-$VERSION.wixpdb"
cd ..

echo ""
echo "Done:"
ls -la dist/AgentScreen.exe "dist/AgentScreen-$VERSION.msi"

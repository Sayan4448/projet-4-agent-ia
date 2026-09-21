param([string]$WixBin = "")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) { throw "Create .venv and install requirements first. See docs/DEVELOPPEMENT.md." }
if (!$WixBin) {
    foreach ($candidate in @("tools\wix311", "$env:WIX\bin", "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin", "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin")) {
        if (Test-Path (Join-Path $candidate "candle.exe")) { $WixBin = (Resolve-Path $candidate).Path; break }
    }
}
if (!$WixBin) { throw "WiX 3 is required. Pass -WixBin pointing to candle.exe/light.exe." }
$Version = & $Python -c "from agent_screen import __version__; print(__version__)"
if ($LASTEXITCODE) { throw "Cannot read version" }
& $Python scripts/make_icon.py
if ($LASTEXITCODE) { throw "Icon generation failed" }
& $Python -m PyInstaller AgentScreen.spec --noconfirm
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Push-Location installer
try {
    & "$WixBin\candle.exe" -arch x64 -o AgentScreen.wixobj AgentScreen.wxs
    if ($LASTEXITCODE) { throw "WiX compilation failed" }
    & "$WixBin\light.exe" -ext WixUIExtension -o "..\dist\Projet4-AgentIA-$Version.msi" AgentScreen.wixobj
    if ($LASTEXITCODE) { throw "MSI linking failed" }
} finally { Pop-Location }
$artifacts = @("dist\AgentScreen.exe", "dist\Projet4-AgentIA-$Version.msi")
$lines = foreach ($file in $artifacts) {
    $hash = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
    "$hash  $(Split-Path $file -Leaf)"
}
$lines | Set-Content "dist\SHA256SUMS.txt" -Encoding ascii
Write-Host "Built $($artifacts -join ', ')"

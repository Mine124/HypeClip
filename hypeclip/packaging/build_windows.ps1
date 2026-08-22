param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = ".\.venv\Scripts\python.exe"

if (!(Test-Path .venv)) { python -m venv .venv }
& $py -m pip install -U pip wheel | Out-Null
& $py -m pip install -r requirements.txt -r packaging\requirements-build.txt

New-Item -ItemType Directory -Force bin, assets | Out-Null
if (!(Test-Path bin\ffmpeg.exe)) {
  $zip = "$env:TEMP\ffmpeg_hypeclip.zip"
  Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip" -OutFile $zip
  Expand-Archive $zip "$env:TEMP\ff_hc" -Force
  Copy-Item "$env:TEMP\ff_hc\*\bin\ffmpeg.exe","$env:TEMP\ff_hc\*\bin\ffprobe.exe" bin\
  Remove-Item $zip,"$env:TEMP\ff_hc" -Recurse -Force -ErrorAction SilentlyContinue
}
if (!(Test-Path packaging\icon.ico)) { & $py packaging\icon.py }
& ".\.venv\Scripts\pyinstaller.exe" packaging\hypeclip.spec --noconfirm `
  --distpath dist --workpath build

if ($SkipInstaller) { exit 0 }
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
         Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$iscc) { Write-Warning "Install Inno Setup 6 first."; exit 1 }
& $iscc packaging\installer.iss
Write-Host "DONE -> dist\installer\HypeClip-Setup.exe" -ForegroundColor Green
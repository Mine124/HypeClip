param([switch]$SkipDeps)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$version = (Select-String -Path hypeclip/config.py `
  -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building HypeClip Portable v$version" -ForegroundColor Cyan
$py = ".\.venv\Scripts\python.exe"

if (!$SkipDeps) {
  if (!(Test-Path .venv)) { python -m venv .venv }
  & $py -m pip install -U pip wheel | Out-Null
  & $py -m pip install -r requirements.txt -r packaging\requirements-build.txt

  New-Item -ItemType Directory -Force bin | Out-Null
  if (!(Test-Path bin\ffmpeg.exe)) {
    $zip = "$env:TEMP\ffmpeg_hypeclip.zip"
    Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip" -OutFile $zip
    Expand-Archive $zip "$env:TEMP\ff_hc" -Force
    Copy-Item "$env:TEMP\ff_hc\*\bin\ffmpeg.exe","$env:TEMP\ff_hc\*\bin\ffprobe.exe" bin\
    Remove-Item $zip,"$env:TEMP\ff_hc" -Recurse -Force -ErrorAction SilentlyContinue
  }
  New-Item -ItemType Directory -Force assets | Out-Null
  if (!(Test-Path packaging\icon.ico)) { & $py packaging\icon.py }
  & ".\.venv\Scripts\pyinstaller.exe" packaging\hypeclip.spec --noconfirm `
    --distpath dist --workpath build
}

$stage = "dist\HypeClip-Portable"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item "dist\HypeClip\*" $stage -Recurse -Force
New-Item -ItemType File -Force "$stage\portable.flag" | Out-Null
foreach ($d in "Data","Data\output","Data\assets\sfx","Data\assets\music",
               "Data\assets\watermarks","Data\app","Data\backups","Data\cache") {
  New-Item -ItemType Directory -Force "$stage\$d" | Out-Null
}
& $py -c "from hypeclip.synth import synthesize_all; synthesize_all('dist/HypeClip-Portable/Data/assets/sfx')"
Set-Content "$stage\Open Output Folder.bat" -Value 'start "" "%~dp0Data\output"' -Encoding ASCII
Copy-Item packaging\portable_README.txt "$stage\README.txt" -Force

$out = "dist\HypeClip-Portable-$version.zip"
if (Test-Path $out) { Remove-Item $out -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $out -CompressionLevel Optimal
$mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
Write-Host "DONE -> $out ($mb MB)" -ForegroundColor Green
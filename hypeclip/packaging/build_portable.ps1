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

  # ---- FFmpeg: try multiple mirrors, survive total failure ----
  New-Item -ItemType Directory -Force bin | Out-Null
  if (!(Test-Path bin\ffmpeg.exe)) {
    $zip = "$env:TEMP\ffmpeg_hypeclip.zip"
    $tmpd = "$env:TEMP\ff_hc"
    $mirrors = @(
      "https://github.com/GyanD/codexffmpeg/releases/latest/download/ffmpeg-release-essentials.zip",
      "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
      "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
      "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    )
    $got = $false
    foreach ($u in $mirrors) {
      try {
        Write-Host "downloading FFmpeg from: $u"
        Invoke-WebRequest $u -OutFile $zip -MaximumRedirection 10 `
          -UserAgent "Mozilla/5.0"
        if ((Get-Item $zip).Length -gt 30MB) { $got = $true; break }
        Write-Warning "file too small, trying next mirror..."
      } catch {
        Write-Warning "mirror failed: $u"
      }
    }
    if ($got) {
      Expand-Archive $zip $tmpd -Force
      $bins = Get-ChildItem -Path $tmpd -Recurse -Include ffmpeg.exe,ffprobe.exe |
              Select-Object -ExpandProperty FullName
      foreach ($b in $bins) { Copy-Item $b bin\ -Force }
      Remove-Item $zip,$tmpd -Recurse -Force -ErrorAction SilentlyContinue
      if (Test-Path bin\ffmpeg.exe) {
        Write-Host "bin\ffmpeg.exe ready" -ForegroundColor Green
      } else {
        Write-Warning "downloaded but exe not found - continuing without bundle"
      }
    } else {
      Write-Warning "All FFmpeg mirrors failed - building WITHOUT bundled ffmpeg."
      Write-Warning "(The app self-downloads FFmpeg into Data\bin on first run.)"
    }
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
if (Test-Path packaging\portable_README.txt) {
  Copy-Item packaging\portable_README.txt "$stage\README.txt" -Force
}

$out = "dist\HypeClip-Portable-$version.zip"
if (Test-Path $out) { Remove-Item $out -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $out -CompressionLevel Optimal
$mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
Write-Host "DONE -> $out ($mb MB)" -ForegroundColor Green

# ============================================================
#  HypeClip portable builder  (full replace - v3, fixes icon path for spec)
#  Run by CI:  powershell -ExecutionPolicy Bypass -File packaging\build_portable.ps1
#  Output:     dist\HypeClip-Portable-<version>.zip
# ============================================================
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "[build] project root: $root"

# ---------- read version ----------
$cfg = Join-Path $root "hypeclip\config.py"
if (-not (Test-Path $cfg)) { throw "hypeclip\config.py not found" }
$v = (Select-String -Path $cfg -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "[build] version v$v"

# ---------- clean ----------
foreach ($d in @("build", "dist")) {
    $p = Join-Path $root $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
$stage = Join-Path $root "build\stage"
New-Item -ItemType Directory -Force -Path $stage | Out-Null

# ---------- python env + deps ----------
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[env] creating virtualenv"
    python -m venv .venv
}
if (-not (Test-Path $venvPy)) { throw "virtualenv python not found at $venvPy" }
Write-Host "[env] venv python: $venvPy"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet
$buildReq = Join-Path $root "packaging\requirements-build.txt"
if (Test-Path $buildReq) {
    & $venvPy -m pip install -r $buildReq --quiet
}
Write-Host "[env] PyInstaller version:"
& $venvPy -m PyInstaller --version

# ---------- locate web UI ----------
$webSrc = $null
$candidate = Join-Path $root "web"
if ((Test-Path $candidate) -and (Test-Path (Join-Path $candidate "index.html"))) {
    $webSrc = $candidate
} else {
    $hit = Get-ChildItem -Path $root -Recurse -Filter "index.html" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\(\.venv|build|dist|node_modules|\.git|\.github)\\' } |
        Select-Object -First 1
    if ($hit) { $webSrc = $hit.Directory.FullName }
}
if (-not $webSrc) { throw "web UI not found: no index.html anywhere in the repo" }
Write-Host "[build] web UI source: $webSrc"

# ---------- ffmpeg (bundled into the zip) ----------
function Get-FFmpeg($destDir) {
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    if ((Test-Path (Join-Path $destDir "ffmpeg.exe")) -and
        (Test-Path (Join-Path $destDir "ffprobe.exe"))) {
        Write-Host "[ffmpeg] already present"; return
    }
    $urls = @(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-lgpl.zip"
    )
    $zip = Join-Path $env:TEMP "ffmpeg_portable.zip"
    $ok = $false
    foreach ($u in $urls) {
        try {
            Write-Host "[ffmpeg] downloading $u"
            Invoke-WebRequest -Uri $u -OutFile $zip -UserAgent "Mozilla/5.0" -MaximumRedirection 10
            if ((Get-Item $zip).Length -gt 10MB) { $ok = $true; break }
        } catch { Write-Host "[ffmpeg] mirror failed: $u" }
    }
    if (-not $ok) { Write-Host "[ffmpeg] WARNING: not bundled - app will download at runtime"; return }
    $tmp = Join-Path $env:TEMP "ffmpeg_extract"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    foreach ($exe in @("ffmpeg.exe", "ffprobe.exe")) {
        $found = Get-ChildItem -Path $tmp -Recurse -Filter $exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { Copy-Item $found.FullName (Join-Path $destDir $exe) -Force }
    }
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[ffmpeg] bundled into $destDir"
}
Get-FFmpeg (Join-Path $stage "Data\bin")

# ---------- icon (generated in root, then copied where the spec expects it) ----------
$icon = Join-Path $root "icon.ico"
if (-not (Test-Path $icon)) {
    try {
        Add-Type -AssemblyName System.Drawing
        $bmp = New-Object System.Drawing.Bitmap 64, 64
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = "AntiAlias"
        $g.Clear([System.Drawing.Color]::FromArgb(255, 17, 21, 38))
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 124, 92, 255))
        $g.FillEllipse($brush, 10, 10, 44, 44)
        $g.Dispose()
        $ico = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
        $fs = [System.IO.File]::Create($icon)
        $ico.Save($fs); $fs.Dispose()
        Write-Host "[icon] icon.ico written"
    } catch { Write-Host "[icon] WARNING: could not generate icon: $_" }
}
# THE FIX: the spec resolves "icon.ico" relative to the packaging folder
Copy-Item $icon (Join-Path $root "packaging\icon.ico") -Force
Write-Host "[icon] copied to packaging\icon.ico for the spec"

# ---------- build with PyInstaller (via venv python, no PATH needed) ----------
$spec = Join-Path $root "packaging\hypeclip.spec"
if (Test-Path $spec) {
    Write-Host "[build] using spec: $spec"
    & $venvPy -m PyInstaller --noconfirm --clean $spec
} else {
    Write-Host "[build] no spec found - building with defaults"
    & $venvPy -m PyInstaller --noconfirm --clean --name HypeClip --icon icon.ico --windowed run_app.py
}
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# ---------- stage the portable folder ----------
$appOut = Join-Path $root "dist\HypeClip"
if (-not (Test-Path $appOut)) {
    $alt = Get-ChildItem (Join-Path $root "dist") -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($alt) { $appOut = $alt.FullName }
}
if (-not (Test-Path $appOut)) { throw "PyInstaller output not found in dist\" }
Copy-Item (Join-Path $appOut "*") $stage -Recurse -Force

# ---------- stage web UI + VERIFY ----------
$webDest = Join-Path $stage "Data\assets\web"
New-Item -ItemType Directory -Force -Path $webDest | Out-Null
Copy-Item (Join-Path $webSrc "*") $webDest -Recurse -Force
$bundlePkg = Join-Path $stage "_internal\hypeclip"
if (Test-Path $bundlePkg) {
    $w2 = Join-Path $bundlePkg "web"
    New-Item -ItemType Directory -Force -Path $w2 | Out-Null
    Copy-Item (Join-Path $webSrc "*") $w2 -Recurse -Force
}
if (-not (Test-Path (Join-Path $webDest "index.html"))) {
    throw "VERIFICATION FAILED: web UI missing from portable stage"
}
Write-Host "[web] staged OK: $webDest"

# ---------- zip ----------
$zip = Join-Path $root "dist\HypeClip-Portable-$v.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
Write-Host ("[done] {0} ({1} MB)" -f $zip, [math]::Round((Get-Item $zip).Length / 1MB, 1))

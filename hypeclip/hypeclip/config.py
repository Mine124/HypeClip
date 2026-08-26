name: Build Portable
on:
  push:
    branches: [main, master]
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - id: loc
        name: Locate project + read version
        shell: pwsh
        run: |
          $f = Get-ChildItem -Recurse -Filter run_app.py |
                 Where-Object { $_.FullName -notmatch '\\(\.|_)' } |
                 Select-Object -First 1
          if (-not $f) {
            Write-Host "::error::run_app.py not found - did the project files get uploaded?"
            exit 1
          }
          $root = $f.Directory.FullName
          Write-Host "Project root: $root"
          "root=$root" >> $env:GITHUB_OUTPUT

          $cfg = Join-Path $root 'hypeclip\config.py'
          if (-not (Test-Path $cfg)) {
            Write-Host "::error::hypeclip/config.py is MISSING in the repo"
            exit 1
          }
          $m = Select-String -Path $cfg -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
          if (-not $m) {
            Write-Host "::error::could not find APP_VERSION = \"x.y.z\" in hypeclip/config.py"
            Write-Host "--- first 10 lines of config.py ---"
            Get-Content $cfg -TotalCount 10 | ForEach-Object { Write-Host $_ }
            exit 1
          }
          $v = $m.Matches[0].Groups[1].Value
          Write-Host "Building v$v"
          "version=$v" >> $env:GITHUB_OUTPUT

      - name: Build portable ZIP
        shell: pwsh
        run: |
          Set-Location "${{ steps.loc.outputs.root }}"
          powershell -ExecutionPolicy Bypass -File packaging\build_portable.ps1

      - name: Attach ZIP to this run
        uses: actions/upload-artifact@v4
        with:
          name: HypeClip-Portable-${{ steps.loc.outputs.version }}
          path: ${{ steps.loc.outputs.root }}/dist/HypeClip-Portable-*.zip
          compression-level: 0
          if-no-files-found: error

      - name: Publish as a Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: v${{ steps.loc.outputs.version }}
          name: HypeClip Portable v${{ steps.loc.outputs.version }}
          body: |
            Portable edition - extract the ZIP anywhere and double-click HypeClip.exe.
            First SmartScreen warning? More info -> Run anyway.
          files: ${{ steps.loc.outputs.root }}/dist/HypeClip-Portable-*.zip

# Mochi setup: creates .venv, installs packages and Playwright's Chromium, makes a desktop shortcut.
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# 1. Find Python 3.11+ (the Microsoft Store "python" stub doesn't count)
$candidates = @(
  (Get-Command py -ErrorAction SilentlyContinue | ForEach-Object { "py -3" }),
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
  (Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'WindowsApps' } | ForEach-Object Source)
) | Where-Object { $_ }
$py = $null
foreach ($c in $candidates) {
  try {
    $v = if ($c -eq 'py -3') { & py -3 -c "import sys;print(sys.version_info[:2]>=(3,11))" } else { & $c -c "import sys;print(sys.version_info[:2]>=(3,11))" }
    if ($v -eq 'True') { $py = $c; break }
  } catch {}
}
if (-not $py) {
  Write-Host "Python 3.11+ not found. Install it with:  winget install Python.Python.3.12" -ForegroundColor Yellow
  exit 1
}
Write-Host "Using Python: $py"

# 2. Virtual environment + packages
if (-not (Test-Path .venv)) {
  if ($py -eq 'py -3') { & py -3 -m venv .venv } else { & $py -m venv .venv }
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -q
.\.venv\Scripts\python.exe -m playwright install chromium

# 3. Folders + personal config
New-Item -ItemType Directory -Force workspace, logs | Out-Null
if (-not (Test-Path config.local.yaml)) { Copy-Item config.local.example.yaml config.local.yaml }

# 4. Offline self-test
.\.venv\Scripts\python.exe -m pytest -q

# 5. Desktop shortcut (opens Windows Terminal if available)
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Mochi.lnk'
if (-not (Test-Path $lnk)) {
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $wt = (Get-Command wt.exe -ErrorAction SilentlyContinue).Source
  if ($wt) { $s.TargetPath = $wt; $s.Arguments = "--title Mochi -d `"$PSScriptRoot`" cmd /k `"$PSScriptRoot\mochi.cmd`"" }
  else     { $s.TargetPath = "$env:ComSpec"; $s.Arguments = "/k `"$PSScriptRoot\mochi.cmd`"" }
  $s.WorkingDirectory = $PSScriptRoot
  $s.IconLocation = "$env:SystemRoot\System32\imageres.dll,-5323"
  $s.Save()
  Write-Host "Created desktop shortcut: $lnk"
}

Write-Host "`nDone! Next: install LM Studio (https://lmstudio.ai), download 'qwen3.6-35b-a3b' (or set another model"
Write-Host "in config.local.yaml), then double-click the Mochi shortcut or run .\mochi.cmd" -ForegroundColor Green

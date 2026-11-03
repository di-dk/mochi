# Mochi setup: creates .venv, installs packages and Playwright's Chromium, makes a desktop shortcut,
# and (optionally) adds the `mochi` command to your PATH.
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1             # full setup
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1 -PathOnly   # only add `mochi` to PATH
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1 -RemovePath # undo the PATH change
param([switch]$PathOnly, [switch]$RemovePath, [switch]$Yes)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Set-MochiPath([bool]$add) {
  # Edits the *user* PATH only (no admin needed), keeping %VARIABLES% unexpanded.
  $dir = $PSScriptRoot.TrimEnd('\')
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
  $old = [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  $parts = @($old -split ';' | Where-Object { $_ })
  $has = $parts | Where-Object { $_.TrimEnd('\') -ieq $dir }
  if ($add -and $has)       { Write-Host "'mochi' is already on your PATH."; $key.Close(); return }
  if (-not $add -and -not $has) { Write-Host "Mochi is not on your PATH."; $key.Close(); return }
  $backup = Join-Path $env:LOCALAPPDATA "mochi-path-backup-$(Get-Date -Format yyyyMMdd_HHmmss).txt"
  Set-Content -Path $backup -Value $old -Encoding utf8
  $new = if ($add) { ($parts + $dir) -join ';' } else { ($parts | Where-Object { $_.TrimEnd('\') -ine $dir }) -join ';' }
  $key.SetValue('Path', $new, [Microsoft.Win32.RegistryValueKind]::ExpandString)
  $key.Close()
  # Notify Explorer/new terminals that the environment changed
  Add-Type -Namespace MochiWin -Name Env -MemberDefinition '[DllImport("user32.dll",CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr h,uint m,UIntPtr w,string l,uint f,uint t,out UIntPtr r);' -ErrorAction SilentlyContinue
  $r = [UIntPtr]::Zero; [void][MochiWin.Env]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$r)
  Write-Host ($(if ($add) { "Added $dir to your user PATH." } else { "Removed $dir from your user PATH." })) -ForegroundColor Green
  Write-Host "Previous PATH backed up to $backup. Open a NEW terminal to use 'mochi'."
}

if ($RemovePath) { Set-MochiPath $false; exit 0 }
if ($PathOnly)   { Set-MochiPath $true;  exit 0 }

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
  $s.IconLocation = "$PSScriptRoot\assets\mochi.ico"
  $s.Save()
  Write-Host "Created desktop shortcut: $lnk"
}

# 6. `mochi` command on PATH (asks first)
$ans = if ($Yes) { 'y' } else { Read-Host "Add the 'mochi' command to your PATH so you can type 'mochi' in any terminal? [Y/n]" }
if ($ans -eq '' -or $ans -match '^[Yy]') { Set-MochiPath $true }

Write-Host "`nDone! Next: install LM Studio (https://lmstudio.ai), download 'qwen3.6-35b-a3b' (or set another model"
Write-Host "in config.local.yaml), then double-click the Mochi shortcut or run .\mochi.cmd" -ForegroundColor Green

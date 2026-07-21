# bootstrap.ps1 -- ONE command that takes a fresh Windows machine to
# doctor-green. PLAN-v3 PR-15: environment bootstrap burned ~25-30% of field
# tokens (hand-driven runtime installs, TTY/creds failures) -- this script
# replaces every "install X by hand" instruction on Windows.
#
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 [-WorkDir DIR]
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Check
#
# Contract (same as bootstrap.sh):
#   * IDEMPOTENT and NON-INTERACTIVE (no prompts, no-TTY-safe).
#   * NEVER requires admin: installs are user-scoped only -- winget with
#     --scope user where the package supports it, scoop (itself a no-admin
#     user-dir install) as the portable route, fnm for node, pip --user for
#     python deps. It never elevates.
#   * Creds flow runs only when SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET (and
#     Tableau PAT vars, where the tableau scripts ship) are already set
#     (ruby scripts/setup.rb --from-env -- values never echoed).
#   * Finishes by running scripts\doctor.ps1 (writes doctor.json -- the report
#     the orchestrator gates on) and writing the bootstrap SENTINEL
#     (~/.sigma-migration/bootstrap.json, + <WorkDir>\bootstrap.json).
#   * -Check = DRY RUN: report what WOULD install, change nothing, skip the
#     doctor (offline-safe). Exit 0 = complete, 1 = pieces missing.
#
# macOS / Linux / Git-Bash users: run scripts/bootstrap.sh instead.
param([switch]$Check, [string]$WorkDir = "")
if (-not $WorkDir -and $env:BOOTSTRAP_WORKDIR) { $WorkDir = $env:BOOTSTRAP_WORKDIR }

$script:Needed = 0
$script:InstallFailed = $false
$script:Actions = @()
$script:PathAdded = @()
$StateDir = Join-Path $env:USERPROFILE ".sigma-migration"

function Okay([string]$m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Plan([string]$piece, [string]$what) {
  $script:Needed++
  if ($Check) { Write-Host "  [X]  $piece" -ForegroundColor Red; Write-Host "       WOULD: $what" -ForegroundColor DarkGray }
  else        { Write-Host "  [X]  $piece" -ForegroundColor Red; Write-Host "       -> $what" -ForegroundColor DarkGray }
}
function Note([string]$m) { Write-Host "       $m" -ForegroundColor DarkGray }

function Activate-PathDir([string]$dir) {
  if (-not $dir -or -not (Test-Path $dir)) { return }
  if (($env:Path -split ';') -contains $dir) { return }
  $env:Path = "$dir;$env:Path"
  if ($Check) { return }
  # Persist USER-scope PATH (never machine scope -- no admin).
  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not (($userPath -split ';') -contains $dir)) {
    [Environment]::SetEnvironmentVariable('Path', "$dir;$userPath", 'User')
  }
  $script:PathAdded += $dir
  $script:Actions += "path-activate: $dir"
}

function Have([string]$exe) { [bool](Get-Command $exe -ErrorAction SilentlyContinue) }
function HaveWinget { Have 'winget' }
function HaveScoop  { Have 'scoop' }

# user-scoped winget install; returns $true on success.
function WingetUserInstall([string]$id) {
  & winget install --id $id -e --scope user --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { return $true }
  # some packages reject --scope user; retry without (per-user default installers)
  & winget install --id $id -e --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
  return ($LASTEXITCODE -eq 0)
}
function ScoopInstall([string]$pkg) {
  & scoop install $pkg 2>&1 | Out-Null
  return ($LASTEXITCODE -eq 0)
}

Write-Host "Environment bootstrap - host: windows (PowerShell)  mode: $(if ($Check) {'check'} else {'full'})`n"

# --- ruby -------------------------------------------------------------------
if (Have 'ruby') { Okay "ruby $((& ruby -e 'print RUBY_VERSION' 2>$null))" }
else {
  # scoop shims / RubyInstaller user dirs that just need PATH activation
  $rubyBin = @(
    (Join-Path $env:USERPROFILE 'scoop\apps\ruby\current\bin'),
    (Get-ChildItem -Path (Join-Path $env:SystemDrive 'Ruby*\bin') -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty FullName)
  ) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'ruby.exe')) } | Select-Object -First 1
  if ($rubyBin) {
    Plan "ruby installed but not on PATH ($rubyBin)" "activate it (user-scope PATH prepend)"
    if (-not $Check) { Activate-PathDir $rubyBin; if (Have 'ruby') { Okay "ruby $((& ruby -e 'print RUBY_VERSION' 2>$null)) (activated)" } }
  } elseif (HaveScoop) {
    Plan "ruby not found" "scoop install ruby (portable, user-dir, no admin)"
    if (-not $Check) {
      if (ScoopInstall 'ruby') { $script:Actions += 'install: ruby (scoop)'; if (Have 'ruby') { Okay "ruby $((& ruby -e 'print RUBY_VERSION' 2>$null)) (scoop)" } else { $script:InstallFailed = $true; Note 'scoop installed ruby but it is not resolvable -- open a new shell and re-run bootstrap' } }
      else { $script:InstallFailed = $true; Note 'scoop install ruby FAILED' }
    }
  } elseif (HaveWinget) {
    Plan "ruby not found" "winget install RubyInstaller.Ruby.3.2 (user scope; no admin)"
    if (-not $Check) {
      if (WingetUserInstall 'RubyInstaller.Ruby.3.2') { $script:Actions += 'install: ruby (winget)'; if (-not (Have 'ruby')) { Note 'winget installed ruby -- a NEW shell may be needed for PATH; re-run bootstrap there' } else { Okay "ruby $((& ruby -e 'print RUBY_VERSION' 2>$null)) (winget)" } }
      else { $script:InstallFailed = $true; Note 'winget install ruby FAILED' }
    }
  } else {
    Plan "ruby not found (no scoop, no winget)" "no admin-free install route -- the USER should install scoop (https://scoop.sh, no admin) and re-run bootstrap"
    if (-not $Check) { $script:InstallFailed = $true }
  }
}

# --- python (real interpreter, not the Store stub) --------------------------
function Test-RealPython($exe, $pre) {
  $cmd = Get-Command $exe -ErrorAction SilentlyContinue
  if (-not $cmd) { return $null }
  if ($exe -ne 'py' -and $cmd.Source -and $cmd.Source.ToLower().Contains('windowsapps')) { return $null }
  try {
    $argsv = @(); if ($pre) { $argsv += $pre }
    $ver = (& $exe @argsv --version 2>&1 | Out-String).Trim()
    if ($ver -notmatch 'Python\s+\d') { return $null }
    return $ver
  } catch { return $null }
}
$script:PyExe = $null; $script:PyPre = $null
if (Test-RealPython 'py' '-3')      { $script:PyExe = 'py'; $script:PyPre = '-3' }
elseif (Test-RealPython 'python' $null)  { $script:PyExe = 'python' }
elseif (Test-RealPython 'python3' $null) { $script:PyExe = 'python3' }
if ($script:PyExe) {
  $pyArgs = @(); if ($script:PyPre) { $pyArgs += $script:PyPre }
  Okay "python $((& $script:PyExe @pyArgs --version 2>&1 | Out-String).Trim() -replace 'Python ','') [$script:PyExe $script:PyPre]"
} else {
  if (HaveScoop) {
    Plan "no real Python (Store stub or none)" "scoop install python (portable, user-dir, no admin)"
    if (-not $Check) {
      if (ScoopInstall 'python') { $script:Actions += 'install: python (scoop)'; if (Test-RealPython 'python' $null) { $script:PyExe = 'python'; Okay 'python (scoop)' } else { $script:InstallFailed = $true; Note 'scoop installed python but it is not resolvable -- open a new shell and re-run bootstrap' } }
      else { $script:InstallFailed = $true; Note 'scoop install python FAILED' }
    }
  } elseif (HaveWinget) {
    Plan "no real Python (Store stub or none)" "winget install Python.Python.3.12 (user scope; no admin)"
    if (-not $Check) {
      if (WingetUserInstall 'Python.Python.3.12') { $script:Actions += 'install: python (winget)'; if (Test-RealPython 'py' '-3') { $script:PyExe = 'py'; $script:PyPre = '-3'; Okay 'python (winget, py -3)' } else { Note 'winget installed python -- a NEW shell may be needed for PATH; re-run bootstrap there' } }
      else { $script:InstallFailed = $true; Note 'winget install python FAILED' }
    }
  } else {
    Plan "no real Python (no scoop, no winget)" "no admin-free install route -- the USER should install scoop (https://scoop.sh) and re-run bootstrap"
    if (-not $Check) { $script:InstallFailed = $true }
  }
}

# pip --user install that survives PEP 668 ("externally-managed-environment"):
# try plain --user, then retry with --break-system-packages. No admin.
function Invoke-PipUserInstall {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Pkgs)
  $a = @(); if ($script:PyPre) { $a += $script:PyPre }
  & $script:PyExe @a -m pip install --user --quiet @Pkgs 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { return $true }
  & $script:PyExe @a -m pip install --user --break-system-packages --quiet @Pkgs 2>&1 | Out-Null
  return ($LASTEXITCODE -eq 0)
}

# --- python deps (doctor's render/similarity checks) ------------------------
if ($script:PyExe) {
  $pyArgs = @(); if ($script:PyPre) { $pyArgs += $script:PyPre }
  & $script:PyExe @pyArgs -c "import PIL, numpy, requests" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { Okay "python deps (Pillow + numpy + requests)" }
  else {
    Plan "python deps missing (Pillow/numpy/requests)" "$script:PyExe $script:PyPre -m pip install --user pillow numpy requests (no admin)"
    if (-not $Check) {
      $ok = Invoke-PipUserInstall pillow numpy requests
      & $script:PyExe @pyArgs -c "import PIL, numpy, requests" 2>$null | Out-Null
      if ($ok -and $LASTEXITCODE -eq 0) { $script:Actions += 'install: pip --user pillow numpy requests'; Okay 'python deps installed (pip --user)' }
      else { $script:InstallFailed = $true; Note 'pip --user install FAILED -- if PEP 668 (externally-managed) the --break-system-packages retry also failed; otherwise check network/proxy' }
    }
  }
  # truststore (best effort): OS trust store so OpenSSL 3.x verifies Looker/Tableau certs
  & $script:PyExe @pyArgs -c "import truststore" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { Okay 'python truststore (OS trust store for TLS)' }
  else {
    Plan "python truststore missing (OpenSSL 3.x TLS vs Looker/Tableau Cloud)" "$script:PyExe $script:PyPre -m pip install --user truststore"
    if (-not $Check) {
      $okt = Invoke-PipUserInstall truststore
      & $script:PyExe @pyArgs -c "import truststore" 2>$null | Out-Null
      if ($okt -and $LASTEXITCODE -eq 0) { $script:Actions += 'install: pip --user truststore'; Okay 'python truststore installed' }
      else { Note 'pip --user install of truststore FAILED -- TLS falls back to certifi/default; install manually if a Looker/Tableau TLS error appears' }
    }
  }
}

# --- node -------------------------------------------------------------------
if (Have 'node') { Okay "node $((& node --version 2>$null))" }
else {
  $fnmNode = Get-ChildItem -Path (Join-Path $env:USERPROFILE '.fnm\node-versions\*\installation') -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty FullName
  if (-not $fnmNode) { $fnmNode = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'fnm\node-versions\*\installation') -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty FullName }
  $scoopNode = Join-Path $env:USERPROFILE 'scoop\apps\nodejs-lts\current'
  if ($fnmNode -and (Test-Path (Join-Path $fnmNode 'node.exe'))) {
    Plan "node installed (fnm) but not on PATH ($fnmNode)" "activate it (user-scope PATH prepend)"
    if (-not $Check) { Activate-PathDir $fnmNode; if (Have 'node') { Okay "node $((& node --version 2>$null)) (activated)" } }
  } elseif (Test-Path (Join-Path $scoopNode 'node.exe')) {
    Plan "node installed (scoop) but not on PATH ($scoopNode)" "activate it (user-scope PATH prepend)"
    if (-not $Check) { Activate-PathDir $scoopNode; if (Have 'node') { Okay "node $((& node --version 2>$null)) (activated)" } }
  } elseif (Have 'fnm') {
    Plan "node not found (fnm present)" "fnm install --lts (user-scoped; no admin)"
    if (-not $Check) {
      & fnm install --lts 2>&1 | Out-Null
      & fnm use --lts 2>&1 | Out-Null
      $fnmNode = Get-ChildItem -Path (Join-Path $env:USERPROFILE '.fnm\node-versions\*\installation'), (Join-Path $env:LOCALAPPDATA 'fnm\node-versions\*\installation') -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty FullName
      if ($fnmNode) { Activate-PathDir $fnmNode }
      if (Have 'node') { $script:Actions += 'install: node LTS (fnm)'; Okay "node $((& node --version 2>$null)) (fnm)" }
      else { $script:InstallFailed = $true; Note 'fnm install --lts did not yield a resolvable node' }
    }
  } elseif (HaveScoop) {
    Plan "node not found" "scoop install nodejs-lts (portable, user-dir, no admin)"
    if (-not $Check) {
      if (ScoopInstall 'nodejs-lts') { $script:Actions += 'install: node (scoop)'; if (Have 'node') { Okay "node $((& node --version 2>$null)) (scoop)" } else { $script:InstallFailed = $true; Note 'scoop installed node but it is not resolvable -- open a new shell and re-run bootstrap' } }
      else { $script:InstallFailed = $true; Note 'scoop install nodejs-lts FAILED' }
    }
  } elseif (HaveWinget) {
    Plan "node not found" "winget install Schniz.fnm, then fnm install --lts (user-scoped; no admin)"
    if (-not $Check) {
      if (WingetUserInstall 'Schniz.fnm') {
        $script:Actions += 'install: fnm (winget)'
        Note 'fnm installed -- a NEW shell may be needed for PATH; re-run bootstrap there to finish node'
        if (Have 'fnm') { & fnm install --lts 2>&1 | Out-Null; if (Have 'node') { Okay "node $((& node --version 2>$null)) (fnm)" } }
      } else { $script:InstallFailed = $true; Note 'winget install Schniz.fnm FAILED' }
    }
  } else {
    Plan "node not found (no fnm, no scoop, no winget)" "no admin-free install route -- the USER should install scoop (https://scoop.sh) and re-run bootstrap"
    if (-not $Check) { $script:InstallFailed = $true }
  }
}

# --- bash (Git Bash -- get-token.sh / *-auth.sh token minting) ---------------
if (Have 'bash') { Okay "bash $((Get-Command bash).Source)" }
else {
  $gitBash = @((Join-Path $env:USERPROFILE 'scoop\apps\git\current\bin'),
               (Join-Path $env:LOCALAPPDATA 'Programs\Git\bin')) |
             Where-Object { Test-Path (Join-Path $_ 'bash.exe') } | Select-Object -First 1
  if ($gitBash) {
    Plan "bash installed (Git for Windows) but not on PATH ($gitBash)" "activate it (user-scope PATH prepend)"
    if (-not $Check) { Activate-PathDir $gitBash; if (Have 'bash') { Okay 'bash (activated)' } }
  } elseif (HaveScoop) {
    Plan "no bash (get-token.sh cannot run)" "scoop install git (ships Git Bash; portable, user-dir, no admin)"
    if (-not $Check) {
      if (ScoopInstall 'git') { $script:Actions += 'install: git/bash (scoop)'; if (Have 'bash') { Okay 'bash (scoop git)' } else { Note 'scoop installed git - open a new shell and re-run bootstrap' } }
      else { $script:InstallFailed = $true; Note 'scoop install git FAILED' }
    }
  } elseif (HaveWinget) {
    Plan "no bash (get-token.sh cannot run)" "winget install Git.Git (user scope; ships Git Bash)"
    if (-not $Check) {
      if (WingetUserInstall 'Git.Git') { $script:Actions += 'install: git/bash (winget)'; if (-not (Have 'bash')) { Note 'winget installed git - a NEW shell may be needed for PATH; re-run bootstrap there' } else { Okay 'bash (winget git)' } }
      else { $script:InstallFailed = $true; Note 'winget install Git.Git FAILED' }
    }
  } else {
    Plan "no bash (no scoop, no winget)" "no admin-free install route - the USER should install scoop (https://scoop.sh) and re-run bootstrap"
    if (-not $Check) { $script:InstallFailed = $true }
  }
}

# --- credentials (non-interactive only; values never echoed) ----------------
$envFile = Join-Path $StateDir 'env'
$hasSigmaFile = (Test-Path $envFile) -and ((Get-Content $envFile -Raw -ErrorAction SilentlyContinue) -match 'SIGMA_CLIENT_ID')
if ($hasSigmaFile) { Okay "Sigma credentials present ($envFile)" }
elseif ($env:SIGMA_CLIENT_ID -and $env:SIGMA_CLIENT_SECRET) {
  Plan "Sigma credentials not yet persisted (env vars ARE set)" "ruby scripts/setup.rb --from-env"
  if (-not $Check) {
    if ((Have 'ruby') -and (Test-Path (Join-Path $PSScriptRoot 'setup.rb'))) {
      & ruby (Join-Path $PSScriptRoot 'setup.rb') --from-env 2>&1 | Out-Null
      if ($LASTEXITCODE -eq 0) { $script:Actions += 'creds: setup.rb --from-env'; Okay 'Sigma credentials persisted from the environment' }
      else { $script:InstallFailed = $true; Note 'setup.rb --from-env FAILED -- check SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET' }
    } else { $script:InstallFailed = $true; Note 'setup.rb (or ruby) unavailable -- re-run bootstrap after ruby resolves' }
  }
} else {
  Plan "Sigma credentials MISSING (no $envFile, no SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET)" "set SIGMA_CLIENT_ID + SIGMA_CLIENT_SECRET (+ SIGMA_BASE_URL) and re-run bootstrap - or the USER runs 'ruby scripts/setup.rb' once in a real terminal"
}
if (Test-Path (Join-Path $PSScriptRoot 'setup-tableau.rb')) {
  $hasTabFile = (Test-Path $envFile) -and ((Get-Content $envFile -Raw -ErrorAction SilentlyContinue) -match 'TABLEAU_PAT_SECRET')
  if ($hasTabFile) { Okay "Tableau credentials present ($envFile)" }
  elseif ($env:TABLEAU_PAT_NAME -and $env:TABLEAU_PAT_SECRET) {
    Plan "Tableau PAT not yet persisted (env vars ARE set)" "ruby scripts/setup-tableau.rb --from-env"
    if (-not $Check) {
      & ruby (Join-Path $PSScriptRoot 'setup-tableau.rb') --from-env 2>&1 | Out-Null
      if ($LASTEXITCODE -eq 0) { $script:Actions += 'creds: setup-tableau.rb --from-env'; Okay 'Tableau credentials persisted from the environment' }
      else { $script:InstallFailed = $true; Note 'setup-tableau.rb --from-env FAILED -- check the TABLEAU_* exports' }
    }
  } else { Note '(Tableau PAT not configured -- WARN-level; set TABLEAU_PAT_NAME/TABLEAU_PAT_SECRET and re-run bootstrap to persist.)' }
}

# --- check mode stops here (no doctor, no writes -- offline-safe) ------------
if ($Check) {
  Write-Host ""
  if ($script:Needed -eq 0) {
    Write-Host "bootstrap -Check: environment COMPLETE - nothing to install. Run bootstrap.ps1 (no -Check) to (re)confirm doctor-green + write the sentinel."
    exit 0
  }
  Write-Host "bootstrap -Check: $($script:Needed) piece(s) missing (listed above). Run bootstrap.ps1 (no -Check) to fix them non-interactively."
  exit 1
}

# --- doctor (writes doctor.json -- the report the orchestrator gates on) -----
Write-Host "`nRunning the environment doctor..."
$doctorArgs = @('-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'doctor.ps1'))
if ($WorkDir) { $doctorArgs += @('-WorkDir', $WorkDir) }
& powershell @doctorArgs
$doctorPass = ($LASTEXITCODE -eq 0)

# --- sentinel ---------------------------------------------------------------
$sentinel = [ordered]@{
  bootstrap_version = 1
  mode              = 'full'
  os                = 'windows'
  actions           = @($script:Actions)
  path_additions    = @($script:PathAdded)
  install_failed    = [bool]$script:InstallFailed
  doctor_pass       = $doctorPass
  completed_at      = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
$json = $sentinel | ConvertTo-Json -Compress -Depth 4
function Write-Sentinel([string]$dest) {
  try {
    $dir = Split-Path -Parent $dest
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    # BOM-less UTF-8 (Ruby's JSON.parse chokes on a BOM) -- same as doctor.ps1.
    [System.IO.File]::WriteAllText($dest, $json, (New-Object System.Text.UTF8Encoding($false)))
  } catch { }
}
Write-Sentinel (Join-Path $StateDir 'bootstrap.json')
if ($WorkDir) { Write-Sentinel (Join-Path $WorkDir 'bootstrap.json') }

Write-Host ""
if ($doctorPass -and -not $script:InstallFailed) {
  Write-Host "bootstrap: COMPLETE - doctor green; sentinel written to $(Join-Path $StateDir 'bootstrap.json')$(if ($WorkDir) { " and $(Join-Path $WorkDir 'bootstrap.json')" })."
  exit 0
}
Write-Host "bootstrap: INCOMPLETE - $(if ($script:InstallFailed) { 'an install step failed; ' })doctor $(if ($doctorPass) { 'green' } else { 'still red' }). Fix the [X] items above and re-run bootstrap.ps1."
exit 1

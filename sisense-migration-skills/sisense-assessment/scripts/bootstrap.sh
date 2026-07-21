#!/usr/bin/env bash
# bootstrap.sh — ONE command that takes a fresh machine to doctor-green
# (macOS / Linux / Windows Git-Bash). PLAN-v3 PR-15: environment bootstrap
# burned ~25–30% of field tokens (hand-driven runtime installs, TTY/creds
# failures) — this script replaces every "install X by hand" instruction.
#
#   bash scripts/bootstrap.sh [--workdir DIR]     # verify + install + creds + doctor
#   bash scripts/bootstrap.sh --check             # DRY RUN: report what WOULD change,
#                                                 # install nothing, touch nothing.
#
# Contract:
#   * IDEMPOTENT — a complete environment no-ops straight into a doctor run.
#   * NON-INTERACTIVE / no-TTY-safe — never prompts; the creds flow runs only
#     when SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET (and Tableau PAT vars, where the
#     tableau scripts ship) are already exported (setup.rb --from-env).
#   * NEVER requires admin — activates runtimes already installed via version
#     managers (rbenv/nvm/fnm/asdf/pyenv, Homebrew keg-only) by prepending
#     their bin dirs, installs via user-scoped Homebrew where present, and
#     pip-installs with --user. It never sudos, never edits system dirs.
#   * Finishes by running scripts/doctor.sh (which writes doctor.json — the
#     report the orchestrator gates on) and writing the bootstrap SENTINEL
#     (~/.sigma-migration/bootstrap.json, + <WORKDIR>/bootstrap.json when
#     --workdir is given). intake.rb / migrate-*.rb refuse to start without it.
#   * --check makes NO network calls and NO writes (doctor is skipped too), so
#     it is testable offline; exit 0 = environment complete, 1 = pieces missing.
#
# Exit codes: 0 complete (env green; full mode: doctor passed + sentinel
# written) · 1 incomplete (check: pieces missing; full: an install failed or
# doctor still red) · 2 usage.
#
# Windows PowerShell users: run scripts\bootstrap.ps1 instead.
set -u

MODE=full
WORKDIR="${BOOTSTRAP_WORKDIR:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check; shift ;;
    --workdir) WORKDIR="${2:-}"; shift 2 ;;
    --workdir=*) WORKDIR="${1#*=}"; shift ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "bootstrap.sh: unknown arg '$1' (supported: --check, --workdir DIR)" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$HOME/.sigma-migration"
PATH_SNIPPET="$STATE_DIR/path.sh"

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) OS=windows-bash ;;
  Darwin) OS=macos ;; Linux) OS=linux ;; *) OS=unknown ;;
esac

NEEDED=0            # pieces the env is missing (check mode: WOULD-do count)
INSTALL_FAILED=0
ACTIONS=""          # newline-joined action log for the sentinel
PATH_ADDED=""       # newline-joined PATH prepends persisted this run

say()  { printf '%s\n' "$*"; }
okay() { printf '  \xe2\x9c\x93 %s\n' "$1"; }
note() { printf '    %s\n' "$1"; }
act()  { ACTIONS="${ACTIONS}${ACTIONS:+
}$1"; }
# missing piece: in --check report WOULD + count; in full mode the caller does
# the install right after (and reports its own outcome).
plan() { # $1 = piece, $2 = what bootstrap does about it
  NEEDED=$((NEEDED+1))
  if [ "$MODE" = check ]; then
    printf '  \xe2\x9c\x97 %s\n     WOULD: %s\n' "$1" "$2"
  else
    printf '  \xe2\x9c\x97 %s\n     \xe2\x86\x92 %s\n' "$1" "$2"
  fi
}

# Prepend a dir to PATH for this run and persist it to ~/.sigma-migration/path.sh
# so later sessions can `source` one file instead of re-diagnosing (doctor's
# node-installed-but-not-on-PATH class). Never touches shell profiles.
activate_path() { # $1 = bin dir
  case ":$PATH:" in *":$1:"*) return 0 ;; esac
  PATH="$1:$PATH"; export PATH
  [ "$MODE" = check ] && return 0
  mkdir -p "$STATE_DIR" 2>/dev/null
  if [ ! -f "$PATH_SNIPPET" ] || ! grep -F "\"$1:\$PATH\"" "$PATH_SNIPPET" >/dev/null 2>&1; then
    printf 'export PATH="%s:$PATH"\n' "$1" >> "$PATH_SNIPPET"
  fi
  PATH_ADDED="${PATH_ADDED}${PATH_ADDED:+
}$1"
  act "path-activate: $1"
}

# Newest matching bin dir from version-manager install layouts (globs sorted, last wins).
latest_bindir() { # $@ = glob patterns of runtime BINARIES; prints the binary's dir
  _lb_out=""
  for _lb_cand in "$@"; do [ -x "$_lb_cand" ] && _lb_out="$_lb_cand"; done
  [ -n "$_lb_out" ] && dirname "$_lb_out"
}

brew_ok() { command -v brew >/dev/null 2>&1; }

# Real-Python probe (rejects the Windows Store alias stub) — same contract as doctor.sh.
py_real() {
  _pr_exe="$1"; shift
  command -v "$_pr_exe" >/dev/null 2>&1 || return 1
  _pr_ver="$("$_pr_exe" "$@" --version 2>&1)" || return 1
  case "$_pr_ver" in Python\ [0-9]*) : ;; *) return 1 ;; esac
  _pr_where="$("$_pr_exe" "$@" -c 'import sys;print(sys.executable)' 2>/dev/null)" || return 1
  case "$(printf '%s' "$_pr_where" | tr 'A-Z' 'a-z')" in *windowsapps*) return 1 ;; esac
  PY_RUN="$_pr_exe${*:+ $*}"
  return 0
}

say "Environment bootstrap — host: $OS  mode: $MODE"
say ""

# Source a previously persisted PATH snippet first: a re-run should see what the
# last bootstrap activated (idempotency).
[ -f "$PATH_SNIPPET" ] && . "$PATH_SNIPPET" 2>/dev/null

# ── ruby ─────────────────────────────────────────────────────────────────────
if command -v ruby >/dev/null 2>&1; then
  okay "ruby $(ruby -e 'print RUBY_VERSION' 2>/dev/null)"
else
  RUBY_DIR="$(latest_bindir \
    "$HOME"/.rbenv/versions/*/bin/ruby \
    "$HOME"/.rubies/*/bin/ruby \
    "$HOME"/.asdf/installs/ruby/*/bin/ruby \
    /opt/homebrew/opt/ruby/bin/ruby \
    /usr/local/opt/ruby/bin/ruby)"
  if [ -n "$RUBY_DIR" ]; then
    plan "ruby installed but not on PATH ($RUBY_DIR)" "activate it (prepend to PATH; persisted in $PATH_SNIPPET)"
    [ "$MODE" = full ] && { activate_path "$RUBY_DIR"; okay "ruby $(ruby -e 'print RUBY_VERSION' 2>/dev/null) (activated from $RUBY_DIR)"; }
  elif brew_ok; then
    plan "ruby not found" "brew install ruby (user-scoped Homebrew; no admin)"
    if [ "$MODE" = full ]; then
      if brew install ruby >/dev/null 2>&1; then
        BREW_RUBY="$(brew --prefix ruby 2>/dev/null)/bin"
        [ -d "$BREW_RUBY" ] && activate_path "$BREW_RUBY"
        act "install: ruby (brew)"
        command -v ruby >/dev/null 2>&1 && okay "ruby $(ruby -e 'print RUBY_VERSION' 2>/dev/null) (brew)" || { INSTALL_FAILED=1; note "brew install ruby finished but ruby still not resolvable"; }
      else
        INSTALL_FAILED=1; note "brew install ruby FAILED — see brew output; re-run bootstrap after fixing"
      fi
    fi
  else
    plan "ruby not found (no version-manager install, no Homebrew)" \
         "no admin-free install route on this host — tell the USER to provide ruby (e.g. install Homebrew or rbenv), then re-run bootstrap"
    [ "$MODE" = full ] && INSTALL_FAILED=1
  fi
fi

# ── python3 ──────────────────────────────────────────────────────────────────
PY_RUN=""
if py_real py -3 || py_real python3 || py_real python; then
  okay "python ($PY_RUN) $($PY_RUN --version 2>&1 | sed 's/^Python //')"
else
  PY_DIR="$(latest_bindir \
    "$HOME"/.pyenv/versions/*/bin/python3 \
    "$HOME"/.asdf/installs/python/*/bin/python3 \
    /opt/homebrew/opt/python@*/bin/python3 \
    /usr/local/opt/python@*/bin/python3)"
  if [ -n "$PY_DIR" ]; then
    plan "python3 installed but not on PATH ($PY_DIR)" "activate it (prepend to PATH; persisted in $PATH_SNIPPET)"
    [ "$MODE" = full ] && { activate_path "$PY_DIR"; py_real python3 && okay "python ($PY_RUN) activated from $PY_DIR"; }
  elif brew_ok; then
    plan "python3 not found" "brew install python (user-scoped Homebrew; no admin)"
    if [ "$MODE" = full ]; then
      if brew install python >/dev/null 2>&1; then
        act "install: python (brew)"
        py_real python3 && okay "python ($PY_RUN) (brew)" || { INSTALL_FAILED=1; note "brew install python finished but python3 still not resolvable"; }
      else
        INSTALL_FAILED=1; note "brew install python FAILED — see brew output; re-run bootstrap after fixing"
      fi
    fi
  else
    plan "python3 not found (no version-manager install, no Homebrew)" \
         "no admin-free install route on this host — tell the USER to provide python3, then re-run bootstrap"
    [ "$MODE" = full ] && INSTALL_FAILED=1
  fi
fi

# pip --user install that survives PEP 668 ("externally-managed-environment",
# e.g. Homebrew/Debian Python): try plain --user first, then retry allowing the
# user-site override. Never sudos, never touches system dirs.
pip_user_install() {
  $PY_RUN -m pip install --user --quiet "$@" >/dev/null 2>&1 && return 0
  $PY_RUN -m pip install --user --break-system-packages --quiet "$@" >/dev/null 2>&1
}

# ── python deps (doctor's render/similarity checks: Pillow + numpy + requests) ─
if [ -n "$PY_RUN" ] || py_real py -3 || py_real python3 || py_real python; then
  if $PY_RUN -c "import PIL, numpy, requests" >/dev/null 2>&1; then
    okay "python deps (Pillow + numpy + requests)"
  else
    plan "python deps missing (Pillow/numpy/requests — renders + the gate-14 visual floor)" \
         "$PY_RUN -m pip install --user pillow numpy requests (user site-packages; no admin)"
    if [ "$MODE" = full ]; then
      if pip_user_install pillow numpy requests \
         && $PY_RUN -c "import PIL, numpy, requests" >/dev/null 2>&1; then
        act "install: pip --user pillow numpy requests"
        okay "python deps installed (pip --user)"
      else
        INSTALL_FAILED=1
        note "pip --user install of pillow/numpy/requests FAILED — if the error was 'externally-managed-environment' (PEP 668) the retry with --break-system-packages also failed; otherwise check network/proxy. Re-run bootstrap when resolved"
      fi
    fi
  fi
  # truststore (best effort): makes Python's TLS use the OS trust store so
  # OpenSSL 3.x verifies Looker/Tableau certs that curl/Ruby already accept.
  # Not required — looker_api/tableau_rest fall back to certifi/default — so a
  # failure here only warns.
  if $PY_RUN -c "import truststore" >/dev/null 2>&1; then
    okay "python truststore (OS trust store for TLS)"
  else
    plan "python truststore missing (OpenSSL 3.x TLS vs Looker/Tableau Cloud)" \
         "$PY_RUN -m pip install --user truststore"
    if [ "$MODE" = full ]; then
      if pip_user_install truststore && $PY_RUN -c "import truststore" >/dev/null 2>&1; then
        act "install: pip --user truststore"
        okay "python truststore installed"
      else
        note "pip --user install of truststore FAILED — TLS falls back to certifi/default; install manually if a Looker/Tableau TLS verification error appears"
      fi
    fi
  fi
fi

# ── node (vendored converters run via node) ──────────────────────────────────
if command -v node >/dev/null 2>&1; then
  okay "node $(node --version 2>/dev/null)"
else
  NODE_DIR="$(latest_bindir \
    "$HOME"/.fnm/node-versions/*/installation/bin/node \
    "$HOME"/.local/share/fnm/node-versions/*/installation/bin/node \
    "$HOME"/.nvm/versions/node/*/bin/node \
    "$HOME"/.asdf/installs/nodejs/*/bin/node \
    "$HOME"/.local/node/bin/node \
    /opt/homebrew/opt/node/bin/node \
    /usr/local/opt/node/bin/node)"
  if [ -n "$NODE_DIR" ]; then
    plan "node installed but not on PATH ($NODE_DIR)" "activate it (prepend to PATH; persisted in $PATH_SNIPPET)"
    [ "$MODE" = full ] && { activate_path "$NODE_DIR"; okay "node $(node --version 2>/dev/null) (activated from $NODE_DIR)"; }
  elif command -v fnm >/dev/null 2>&1; then
    plan "node not found (fnm present)" "fnm install --lts (user-scoped; no admin)"
    if [ "$MODE" = full ]; then
      if fnm install --lts >/dev/null 2>&1; then
        NODE_DIR="$(latest_bindir "$HOME"/.fnm/node-versions/*/installation/bin/node "$HOME"/.local/share/fnm/node-versions/*/installation/bin/node)"
        [ -n "$NODE_DIR" ] && activate_path "$NODE_DIR"
        act "install: node LTS (fnm)"
        command -v node >/dev/null 2>&1 && okay "node $(node --version 2>/dev/null) (fnm)" || { INSTALL_FAILED=1; note "fnm installed node but it is still not resolvable"; }
      else
        INSTALL_FAILED=1; note "fnm install --lts FAILED — re-run bootstrap when the network allows"
      fi
    fi
  elif brew_ok; then
    plan "node not found" "brew install node (user-scoped Homebrew; no admin)"
    if [ "$MODE" = full ]; then
      if brew install node >/dev/null 2>&1; then
        act "install: node (brew)"
        command -v node >/dev/null 2>&1 && okay "node $(node --version 2>/dev/null) (brew)" || { INSTALL_FAILED=1; note "brew install node finished but node still not resolvable"; }
      else
        INSTALL_FAILED=1; note "brew install node FAILED — see brew output; re-run bootstrap after fixing"
      fi
    fi
  else
    plan "node not found (no version-manager install, no Homebrew, no fnm)" \
         "no admin-free install route on this host — tell the USER to provide node 18+ (e.g. install Homebrew or fnm), then re-run bootstrap"
    [ "$MODE" = full ] && INSTALL_FAILED=1
  fi
fi

# ── credentials (non-interactive only — setup.rb --from-env; never a prompt) ─
NEUTRAL_ENV="$STATE_DIR/env"
if [ -f "$NEUTRAL_ENV" ] && grep -q 'SIGMA_CLIENT_ID' "$NEUTRAL_ENV" 2>/dev/null; then
  okay "Sigma credentials present ($NEUTRAL_ENV)"
elif [ -n "${SIGMA_CLIENT_ID:-}" ] && [ -n "${SIGMA_CLIENT_SECRET:-}" ]; then
  plan "Sigma credentials not yet persisted (env vars ARE exported)" \
       "ruby scripts/setup.rb --from-env (persists them; values never echoed)"
  if [ "$MODE" = full ]; then
    if [ -f "$HERE/setup.rb" ] && command -v ruby >/dev/null 2>&1 && ruby "$HERE/setup.rb" --from-env >/dev/null 2>&1; then
      act "creds: setup.rb --from-env"
      okay "Sigma credentials persisted from the environment (setup.rb --from-env)"
    else
      INSTALL_FAILED=1; note "setup.rb --from-env FAILED — check SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET exports"
    fi
  fi
else
  plan "Sigma credentials MISSING (no $NEUTRAL_ENV, no SIGMA_CLIENT_ID/SIGMA_CLIENT_SECRET in the env)" \
       "export SIGMA_CLIENT_ID + SIGMA_CLIENT_SECRET (+ SIGMA_BASE_URL) and re-run bootstrap — or the USER runs 'ruby scripts/setup.rb' once in a real terminal"
  # Not an install failure: bootstrap cannot invent credentials. Doctor will
  # fail-close on them below, keeping the run honestly red until they exist.
fi

# Tableau PAT (only where the tableau scripts ship next to this bootstrap).
if [ -f "$HERE/setup-tableau.rb" ]; then
  if [ -f "$NEUTRAL_ENV" ] && grep -q 'TABLEAU_PAT_SECRET' "$NEUTRAL_ENV" 2>/dev/null; then
    okay "Tableau credentials present ($NEUTRAL_ENV)"
  elif [ -n "${TABLEAU_PAT_NAME:-}" ] && [ -n "${TABLEAU_PAT_SECRET:-}" ]; then
    plan "Tableau PAT not yet persisted (env vars ARE exported)" "ruby scripts/setup-tableau.rb --from-env"
    if [ "$MODE" = full ]; then
      if command -v ruby >/dev/null 2>&1 && ruby "$HERE/setup-tableau.rb" --from-env >/dev/null 2>&1; then
        act "creds: setup-tableau.rb --from-env"
        okay "Tableau credentials persisted from the environment"
      else
        INSTALL_FAILED=1; note "setup-tableau.rb --from-env FAILED — check TABLEAU_PAT_NAME/TABLEAU_PAT_SECRET/TABLEAU_SITE_CONTENT_URL/TABLEAU_SERVER_URL exports"
      fi
    fi
  else
    note "(Tableau PAT not configured — WARN-level; needed only for Tableau discovery. Export TABLEAU_PAT_NAME/TABLEAU_PAT_SECRET and re-run bootstrap to persist.)"
  fi
fi

# ── check mode stops here (no doctor, no writes — offline-safe) ──────────────
if [ "$MODE" = check ]; then
  say ""
  if [ "$NEEDED" -eq 0 ]; then
    say "bootstrap --check: environment COMPLETE — nothing to install. Run 'bash scripts/bootstrap.sh' to (re)confirm doctor-green + write the sentinel."
    exit 0
  fi
  say "bootstrap --check: $NEEDED piece(s) missing (listed above). Run 'bash scripts/bootstrap.sh' to fix them non-interactively."
  exit 1
fi

# ── doctor (writes doctor.json — the report the orchestrator gates on) ───────
say ""
say "Running the environment doctor…"
if [ -n "$WORKDIR" ]; then
  bash "$HERE/doctor.sh" --workdir "$WORKDIR"
else
  bash "$HERE/doctor.sh"
fi
DOCTOR_EXIT=$?
DOCTOR_PASS=false
[ "$DOCTOR_EXIT" -eq 0 ] && DOCTOR_PASS=true

# ── sentinel ─────────────────────────────────────────────────────────────────
jstr() { _js="${1:-}"; _js="$(printf '%s' "$_js" | sed 's/\\/\\\\/g; s/"/\\"/g')"; printf '%s' "$_js"; }
json_lines() { # newline-joined $1 -> JSON string array items
  _jl_out=""
  while IFS= read -r _jl_line; do
    [ -z "$_jl_line" ] && continue
    _jl_out="${_jl_out}${_jl_out:+,}\"$(jstr "$_jl_line")\""
  done <<EOF
$1
EOF
  printf '%s' "$_jl_out"
}
write_sentinel() {
  _ws_dest="$1"
  mkdir -p "$(dirname "$_ws_dest")" 2>/dev/null || return 0
  {
    printf '{'
    printf '"bootstrap_version":1,'
    printf '"mode":"full",'
    printf '"os":"%s",' "$(jstr "$OS")"
    printf '"actions":[%s],' "$(json_lines "$ACTIONS")"
    printf '"path_additions":[%s],' "$(json_lines "$PATH_ADDED")"
    printf '"install_failed":%s,' "$([ "$INSTALL_FAILED" -eq 0 ] && echo false || echo true)"
    printf '"doctor_pass":%s,' "$DOCTOR_PASS"
    printf '"completed_at":"%s"' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '}\n'
  } > "$_ws_dest" 2>/dev/null || true
}
write_sentinel "$STATE_DIR/bootstrap.json"
[ -n "$WORKDIR" ] && write_sentinel "$WORKDIR/bootstrap.json"

say ""
if [ -n "$PATH_ADDED" ]; then
  say "PATH additions persisted to $PATH_SNIPPET — new shells outside bootstrap: 'source $PATH_SNIPPET'."
fi
if [ "$DOCTOR_PASS" = true ] && [ "$INSTALL_FAILED" -eq 0 ]; then
  say "bootstrap: COMPLETE — doctor green; sentinel written to $STATE_DIR/bootstrap.json${WORKDIR:+ and $WORKDIR/bootstrap.json}."
  exit 0
fi
say "bootstrap: INCOMPLETE — $( [ "$INSTALL_FAILED" -ne 0 ] && printf 'an install step failed; ' )doctor exit $DOCTOR_EXIT. Fix the ✗ items above (doctor names each) and re-run: bash scripts/bootstrap.sh"
exit 1

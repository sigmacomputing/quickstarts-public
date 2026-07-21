# Environment & Windows setup

**Run the bootstrap first — it is the ONLY sanctioned way to fix a missing
runtime.** One idempotent, non-interactive command takes a fresh machine to
doctor-green (verify/activate/install ruby + python3 + pip deps + node, persist
creds from env vars, run the doctor, write the bootstrap sentinel):

- macOS / Linux / **Git Bash**: `bash scripts/bootstrap.sh`
- **Windows PowerShell**: `powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1`
- Dry run (report what WOULD install, change nothing): `bash scripts/bootstrap.sh --check`
  / `bootstrap.ps1 -Check`

It never requires admin (user-scoped winget/scoop on Windows; brew/rbenv/fnm
version-manager activation elsewhere; `pip --user` for Python deps), never
prompts (no-TTY-safe), and never echoes credential values. `intake.rb` and the
orchestrators refuse to start until the bootstrap sentinel + a passing
`doctor.json` exist — so run it once per machine, before anything else.

**Agents: NEVER hand-install a runtime.** Do not `brew install` / `apt-get` /
`winget install` / download binaries or edit PATH yourself — run the bootstrap
and show the user its output. If the bootstrap reports no admin-free route on
the host, that message is for the **user** to act on; surface it and stop.

**The doctor** (`bash scripts/doctor.sh` / `scripts\doctor.ps1`) is the
verify-only half: it reports what's installed and writes the `doctor.json`
fingerprint the orchestrator gates on. The bootstrap runs it for you as its
final step. Exit 0 = good to go; every ✗/[X] line's remediation is the
bootstrap one-liner above.

## Required runtimes
| Tool | Used by | Notes |
|---|---|---|
| **ruby** | the `*-to-sigma` orchestrators (tableau, qlik, powerbi, quicksight, cognos) | not preinstalled on Windows |
| **python 3** | looker / thoughtspot / microstrategy / sisense entrypoints + all discovery scripts | **Windows: the Store-alias stub bites — see below** |
| **node 18+** | the vendored converters (`converter/*.mjs`) and `*.mjs` build steps | often installed-but-not-on-PATH (version managers) — bootstrap activates it |
| **bash** | `get-token.sh`, `*-auth.sh` (Sigma token minting) | Windows: Git Bash (bootstrap.ps1 installs Git user-scoped if absent) |

## Windows footguns (what the bootstrap handles for you)

1. **Python "Store stub."** A bare `python` / `python3` on Windows usually resolves to
   the Microsoft Store *App Execution Alias* — a stub that silently does nothing when
   run non-interactively (commands "hang or exit with no output"). The doctor and
   bootstrap both detect and reject the stub (they probe `py -3` first and refuse any
   interpreter under `WindowsApps`); `bootstrap.ps1` installs a real user-scoped Python
   when none exists. The skills' scripts are already hardened: Ruby/Node spawns resolve
   a real Python (skipping the stub), and Python entrypoints re-spawn via
   `sys.executable` — so after bootstrap, use `py -3 scripts/<x>.py` for hand-driven calls.

2. **No `bash`.** The Sigma token step (`eval "$(scripts/get-token.sh)"`) is a bash
   script; cmd/PowerShell alone can't run it. `bootstrap.ps1` installs Git for Windows
   (which ships Git Bash) user-scoped when no bash is present. Run the `*.sh` helpers
   from Git Bash (or WSL).

3. **CRLF line endings.** If `git config core.autocrlf` is `true`, checkout can rewrite
   the shipped `.sh`/`.rb`/`.py` to CRLF and break shebangs (`\r: command not found`).
   Set `git config --global core.autocrlf input` and re-checkout (the doctor flags this).

4. **Ruby not on PATH.** `bootstrap.ps1` activates an existing RubyInstaller/scoop ruby
   or installs one user-scoped (winget/scoop) — no admin, no manual PATH surgery.

5. **Node installed but invisible / no admin rights.** Version managers (fnm/nvm) activate
   via interactive-shell profile hooks an agent shell never sources — so node is often
   installed yet "not found" (field-caught twice on one machine). The bootstrap probes the
   standard version-manager dirs and activates the install (persisting the PATH prepend to
   `~/.sigma-migration/path.sh`); when node is genuinely absent it installs user-scoped
   (fnm/scoop/brew) with a pinned LTS — never an unpinned "latest" download, never admin.

> The converters themselves need **no clone, no `npm install`, no network, no MCP** —
> each skill ships a self-contained `converter/*.mjs` bundle run via `node`. So the
> whole environment story is: run the bootstrap once, read the doctor's output.

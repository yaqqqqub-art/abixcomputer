# ABIX AI - Stage A (audit) and Stage B (design)

Date: 2026-11-13. Base: ABIX Cloud Computer Stage 5. Backup of the untouched Stage 5 tree: `abix-backup-stage5-original/`.

## 1. What was actually checked

| Check | Result |
|---|---|
| Read README, STAGE1-5, SECURITY, DEPLOYMENT, compose, Dockerfile, supervisord, entrypoint, nginx, abix_api.py, abix_apps.py, frontend | done |
| `tests/unit/test_apps.py` (18) | PASS |
| `tests/unit/test_backend.py` (15) | PASS |
| `tests/unit/test_frontend_ids.py` (6) | PASS |
| `test_pointer.js`, `test_osk.js` | PASS |
| `tests/unit/test_abix_ctl.sh` (32) | PASS 32/0 |
| `tests/ui/test_ui.py` (30, real Chromium, fake noVNC page) | PASS 0 failed |
| `tests/smoke.sh` (needs Docker) | NOT RUN here: no Docker in this sandbox |
| Docker image build | NOT RUN here |
| Real deployment | The screen recording you sent shows ABIX running through a Cloudflare quick tunnel with Firefox working, so the stack runs on your server |

Baseline: every test that can run here passes. This is the zero-regression reference for all later stages.

## 2. Feature status (verified from code, not from folder names)

Implemented: web login (PBKDF2, signed cookie, idle/absolute expiry, rate limit), lock screen with VNC cut-off, settings (theme, animation, accent, wallpaper), power actions, file browse/download/upload/mkdir (confined to the home folder), App Center (apt/.deb catalog + SSRF-hardened Wine .exe download), noVNC desktop, mouse modes, on-screen keyboard, clipboard bridge, Cloudflare tunnel compose file.

Not implemented (folders are README-only stubs): terminal API, file rename/move/delete/edit API, multi-user accounts, monitoring, database, backup/recovery, any AI.

## 3. Findings that shape the AI design

| # | Finding | Consequence |
|---|---|---|
| 1 | `abix_api.py` runs as **root** in the container (stdlib `ThreadingHTTPServer`) | The AI must NOT run inside this process. A separate agent service is needed, and no tool call may ever run as root. |
| 2 | Secrets live in `/etc/abix/backend.json` (root, 600), good pattern | The Anthropic key goes to a separate root-only file `/etc/abix/ai.json`, never to the desktop user's environment, never to the browser. |
| 3 | The desktop user `abix` owns `~/.vnc/passwd` and the whole home | Any shell the AI runs as `abix` can read that file. Acceptable only because VNC is localhost-bound; documented as a known limit. AI memory/task database must live OUTSIDE the home (new volume, root-owned) so a prompt-injected command cannot rewrite it. |
| 4 | `cap_drop: ALL` + `no-new-privileges` | `sudo` cannot work, which is good. "Install approved software" must go through the existing App Center catalog path (allow-list), with user approval. |
| 5 | No Docker socket in the container (deliberate) | The AI cannot run `docker`/`docker compose` for real inside ABIX. Docker will be taught with explanations and files, not live containers. Stated as a limitation, not hidden. |
| 6 | Image has no `xdotool`, `wmctrl`, `scrot`/ImageMagick, AT-SPI python bindings, Playwright, Anthropic SDK | Must be added to the Dockerfile (Stage C/E/F). |
| 7 | Outbound internet is unrestricted from the container | Prompt-injection from web pages could exfiltrate data. The agent browser/fetch tools will reuse the `public_ip` / `check_url` rules from `abix_apps.py` (https only, public addresses only, pinned IP). |
| 8 | One shared account, no 2FA, sessions in RAM, reachable from the internet via the tunnel | An AI that controls the machine raises the stakes of this single password. Mitigation: approval gates for risky actions, kill switch, per-task action budget, audit log. 2FA is recommended later (outside this scope unless you want it). |
| 9 | Nginx `client_max_body_size 16k`, API has no streaming route | Add `/api/ai/` with `proxy_buffering off` for live progress (server-sent events). Screenshots are served only through an authenticated endpoint. |
| 10 | Strict CSP: `script-src 'self'`, no inline scripts | Dashboard must be external JS files. Model/web text must be rendered with `textContent` or a small safe renderer, never `innerHTML` (XSS from AI or web content). |
| 11 | Video: the desktop does not fill the browser window (black bars) | Existing cosmetic issue, low priority, not part of the AI work. Will not be touched unless you ask. |
| 12 | README still says "written, untested" for items the video shows working | Docs will be updated honestly in Stage L. |

No security bug was found in the existing login, CSRF, path-safety or download code during this read; the tests cover path traversal, symlink escape and SSRF cases. This is a code-reading and test-based statement, not a penetration test.

## 4. Stage B design (agreed defaults, change if you object)

```
Browser (dashboard, external JS, no keys)
   |  HTTPS, session cookie + X-Abix CSRF header (same as today)
Nginx  --/api/ai/-->  abix_agent.py   (separate supervisord program, own port 8090, internal only)
                         |- orchestrator: agent loop UNDERSTAND>PLAN>EXECUTE>OBSERVE>VERIFY>CORRECT>COMPLETE
                         |- providers/   base.py, anthropic.py (official SDK, tool use), later others
                         |- tools/       terminal, files, browser(Playwright), research, desktop(xdotool+AT-SPI), install_app
                         |- policy.py    risk classes: safe / needs-approval / forbidden
                         |- store.py     SQLite (tasks, steps, memory, learning progress, audit log, usage)
                         '- every tool process is spawned as user abix (privileges dropped), with timeout + ulimits
Secrets: /etc/abix/ai.json (root 600). State: /var/lib/abix-ai on a new named volume (root-owned).
```

Decisions and why:
- **Separate service, stdlib HTTP like the current API**, plus the official `anthropic` SDK in a venv. Keeps the current API untouched (zero regression).
- **Provider interface** `Provider.run_turn(messages, tools) -> events`, so other models are an extra file. Default model comes from `ABIX_AI_MODEL`; exact model and computer-use tool versions will be checked against Anthropic's current docs in Stage C instead of being taken from memory.
- **Risk policy (enforced in code, not in the prompt):** forbidden = anything touching `/etc/abix`, other users, privilege escalation, raw disk, firewall; needs approval (UI button, expires) = delete, overwrite, `rm -r`, chmod/chown broad, installs, network downloads of executables, anything outside the home; safe = read, list, create new files in the home, screenshots, web reading. Commands run as an argument list or via a restricted `bash -c` after policy checks, never with string-built shell from web content.
- **Untrusted content:** text from web pages/files is wrapped and labelled as data in the model context; tool calls that come right after reading untrusted content on a risky action always require approval.
- **Stop button:** a cancel flag checked between every step plus process-group kill of the running tool, target under 2 seconds.
- **Computer control order of preference:** AT-SPI/browser automation first, then xdotool with screenshots. A step counts as done only after a verification observation (screenshot diff, file exists, exit code), not after the click.
- **Memory:** SQLite, per-user rows, visible and deletable in the UI, secret-pattern filter before saving (API keys, passwords, tokens are refused), de-duplication by normalised text.
- **Teaching:** Bangla explanations with English terms live in tutor system prompts and a lesson/progress tables; no fake content, all answers come from the model.

## 5. Staged plan and exit criteria

| Stage | Output | Exit test |
|---|---|---|
| C | agent service, store, Anthropic provider, SSE, auth reuse | unit tests with a fake provider; real call test needs your key (procedure provided) |
| D | terminal + file tools + policy + approvals | tests for injection, escape, timeout, cancel |
| E | browser + research tools | tests against a local web server; real-web test needs internet |
| F | desktop control | real xdotool test on Xvfb (available here) if packages can be installed; otherwise documented procedure |
| G | memory + task manager | persistence and restart-recovery tests |
| H/I | Computer teacher, English tutor | lesson/progress logic tests; content quality needs your review |
| J | dashboard | Chromium UI tests, no JS errors |
| K | full regression + security pass | all Stage 5 tests still green |
| L | docs, Bangla guide, env template, backup/recovery | clean build instructions |

## 6. Limits of the build environment (this sandbox)

No Docker, no Xtigervnc, no outbound internet, no Anthropic key. So here I can test unit and integration logic, Chromium UI, and (if tools are present) X11 control on Xvfb. I cannot test the real Claude API, the Docker image build, or live web research; each gets an exact test procedure for your server.

## 7. Update (user decision): own model only, no Claude, no Ollama

The model is trained by the owner on their own GPU (RTX 5060 Ti, 16 GB) from a data file, starting from a free open-weights base model (training from zero is not possible in 2 hours). It is served by a plain OpenAI-compatible server such as llama.cpp `llama-server`. This replaces the Anthropic parts of sections 3 (finding 2, 6), 4 and 5:
- No `anthropic` SDK, no `/etc/abix/ai.json` API key. The model address is `ABIX_AI_URL` (+ optional `ABIX_AI_MODEL`).
- Small models cannot be trusted with raw pixel clicking: Stage F numbers the buttons found by AT-SPI/browser automation and the model picks a number.
- Tool calls use one JSON object per turn parsed by `backend/ai/agent.py`; invalid output is corrected twice, then the task fails (never guessed).
- Stage C done: `backend/ai/` (store, providers, agent loop), `tests/unit/test_ai_core.py` (16 tests). Not done yet: HTTP service wrapper, Nginx route, supervisord entry, real tools.

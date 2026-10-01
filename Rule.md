# Rule_online.md — AI Coding Rules for the `online` Branch

> **Branch purpose**: This branch hosts the **production web application** deployed on **Heroku** at [https://www.easyokapi.cbbiotec.vn/](https://www.easyokapi.cbbiotec.vn/). It is a **multi-user, server-hosted** version — users access it through their browser with no local installation.

---

## 1. Project Identity

| Field | Value |
|---|---|
| **App name** | Easy OKAPI |
| **Domain** | Colorimeter data visualization for bio-sensor experiments |
| **Framework** | Flask (Python 3.12.11) + Jinja2 templates |
| **Real-time** | Flask-SocketIO with eventlet async mode |
| **Deployment** | Heroku (`Procfile`: `gunicorn -k eventlet --workers 1 main:app`) |
| **Runtime** | `runtime.txt` → `python-3.12.11` |
| **Live URL** | `https://www.easyokapi.cbbiotec.vn/` |

---

## 2. Critical Rules for AI Coding

### 2.0 Mandatory First Step: Read EASY OKAPI.md

- **BEFORE executing any commands like `ls -R` or `find` to explore the codebase**, you **MUST** read `easyokapi-knowledge/EASY OKAPI.md` first.
- This document holds the full functional summary, architecture, codebase maps, and directory structure of the project. Prioritizing reading this prevents wasting tokens on excessive directory listings and codebase guessing.

### 2.1 Data Storage — NEVER Use Local Filesystem for User Data

- All user CSV and JSON data must go through `get_user_data()` → in-memory `USER_DATA` dict.
- **Never** use `open()`, `os.path`, or `Path` to read/write user files on the server filesystem.
- Default sample data (`csv/multi.csv`, `csv/single.csv`, `json/exp_kinetics.json`, `json/exp_point.json`) is loaded into memory on first request via `init_user_data()`.

### 2.2 Multi-User Session Isolation

- Every route that accesses user data **must** call `get_user_data()` (which internally calls `get_user_id()` to get the session-bound `user_id`).
- Never use global variables to store per-user state outside of `USER_DATA`.
- Use `user_csv_lock` for thread-safe CSV export operations.

### 2.3 Static Files & Build

- **Development source** is in `static/script/` (JS) and `static/style.css` (CSS).
- **Production serves the minified copies out of `static/dist/`**, but the Flask static folder is plain `static/` (`main.py`: `Flask(__name__, static_folder='static')`) — `index.html` picks `dist/style.min.css` over `style.css` on `config.PRODUCTION_MODE`. So a URL **inside** a stylesheet resolves against `/static/dist/` in production and `/static/` in development: write it rooted (`url("/static/okapi-run.gif")`), never relative, or it 404s in exactly one of the two modes.
- After modifying any JS or CSS, you **must** run `npm run build` before deploying.
- **Never** edit files in `static/dist/` directly — they are generated artifacts.
- **There is one loading animation, and it is the okapi running** (`static/okapi-run.gif`, transparent, self-looping) — `.okapi-loader` behind `#global-spinner`, matching the desktop branch. **Reduced motion swaps the asset, it does not stop the animation**: a GIF carries its own frames and no `animation-duration` override can pause them, so `prefers-reduced-motion: reduce` repoints the image at `okapi.png`. **Anti-pattern**: adding a fresh border-ring spinner for a new wait.
- The `index.html` template references scripts via `{{ url_for('static', ...) }}` which resolves to `static/dist/`.

### 2.4 No HID / No Local Hardware

- This branch has **no HID logging** functionality. Do not add USB/serial device communication code.
- The `/api/current_output` endpoint returns `{"exists": False}`.
- Any references to `log_hid_data.py`, `script_monitor.py`, `browser_mgt.py`, or `send_command.py` are **not present** on this branch.

### 2.5 Google Drive Integration

- OAuth uses encrypted credentials (`credentials.enc`) decrypted with `GOOGLE_ENCRYPTION_KEY`.
- Session recovery logic handles cross-site cookie drops by encoding `user_id` in the OAuth `state` parameter.
- Google Drive operations are in `src/google_drive_service.py`; UI logic in `static/script/drive-integration.js`.
- Drive mode states: `guest` (default, uses sample data) → `connected` (uses Drive-synced data).

### 2.6 Real-Time Updates

- The app uses **Flask-SocketIO** with **eventlet** for real-time UI updates.
- After any CRUD operation on user files, emit the corresponding socket event:
  - CSV changes: `socketio.emit('update_csv')`
  - JSON changes: `socketio.emit('update_json', {'mode': mode})`
- The Heroku Procfile uses `-k eventlet --workers 1` — **only 1 worker** is allowed with SocketIO.

### 2.7 Frontend Conventions

- **Global state** lives in `AppState` object (defined in `index.js`).
- Use utility short-hands from `short-hands.js` (`$id`, `$text`, `$hidden`, `$toggleClass`, `fetchJSON`).
- SweetAlert2 (`Swal`) is used for dialogs and confirmations (loaded via CDN in `index.html`).
- Chart.js is used for plotting (loaded via CDN).
- MathJax is used for rendering mathematical equations.
- **Light/dark theme** is toggled via `body.light` / `body.dark` classes.
- Three measurement modes: `kinetics`, `point`, `calibrate`. Mode switching triggers `switchingModes()` and `switchingCalModes()`.
- "Source" terminology is used (not "sensor") for data sources.
- **Saturation (Sat) requires a confirmed plateau**: `math_ops.calculate_kinetics_quantities` reports `saturationValue`/`timeToSaturation` only when a real plateau is found — the segment after the linear region must hold `>= max(3, window_size // 2)` points **and** have its own linear slope `<= SAT_FLAT_FRACTION` (0.10) of `max_rate` (`_tail_is_flat`). If the trace was interrupted while still rising, the tail is too short, or no linear region exists, Sat is `"--"` — never a median of still-rising or arbitrary data. Max rate + linear region are still reported. The JS Sat display keys off `saturationValue === "--"` (`data-display.js`), not `timeToSaturation !== null`. Covered by `test_calc_kinetics_*` in `tests/test_math_ops.py`. Do not emit a Sat number without the flatness gate.
- **Skeleton vs spinner vs busy — three different promises.** `showSkeleton(target, opts)` /
  `hideSkeleton(target)` (`static/script/skeleton.js`, loaded in `<head>`) mark a region
  whose **content is being fetched**: the file/JSON tables on a mode switch, the chart on
  a file load, the report item list. `window.showSpinner()`/`hideSpinner()` (the
  `#global-spinner` overlay) stays for a **blocking operation** — merge, export, report
  build. Do not swap one for the other: an overlay says "something is running", a skeleton
  says "content is arriving here". Nothing paints before a 200 ms delay, so a fast response
  never flashes a placeholder; the host carries `aria-busy="true"` while one is up, since
  the bars announce nothing themselves. Shapes are built from the single `.skel` primitive
  in `style.css` — do not hand-draw per-component skeletons. Clear one **at the line that
  paints the real content**, not when the fetch resolves (`updateFileTable` renders only
  after `filterFiles()` finishes its own round trips).
  - **The third member is `.is-busy`, and it exists for work started inside an open
    dialog.** `#global-spinner` is `z-index: 15000`, *deliberately* above SweetAlert, so
    showing it for an action taken in a dialog scrims the dialog the user is working in —
    `confirmSwalItemDelete` dims and disables the one card instead. For the same reason,
    a handler that shows the spinner and then opens a `Swal` must **hide it before the
    dialog opens**, not only in a trailing `finally` (`revealDownloadToken`,
    `deleteAccount` in `index.html` drop it right after the response is parsed).
  - **A big download reports its size; `await` it or the overlay is a lie.** `/get_data`
    expands a CSV into a JSON array of row objects, so a long measurement arrives as
    several MB. `fetchJSONProgress()` (`short-hands.js`) streams the body through a
    reader and calls back with bytes received, driving `setSpinnerProgress()` /
    `setSpinnerDetail()`; below **512 KB** nothing is drawn, because a percentage that
    flashes straight to 100 reads as a glitch (skeleton.js's `DELAY_MS`, measured in
    bytes). `totalBytes` is **null** whenever a percentage would be a guess — no
    `Content-Length`, or an encoded body, where the header counts compressed bytes and
    the reader hands back decoded ones — and the caller then shows movement, not a
    position. The readout updates once per whole percent, and `#spinner-detail` carries
    `aria-live="off"` to opt out of the overlay's polite region: a hundred announcements
    would bury the one status message that matters. **The bug this was built on top of:**
    `processDataDisplay` called the async `fetchData` without `await` and without being
    async itself, so `await processDataDisplay(...)` in `selectFile` resolved on
    `undefined` and its `finally` dropped the spinner *while the file was still
    downloading* — the larger the file, the longer the page sat with no overlay at all.
    **Anti-pattern**: an async helper called bare from a function whose `finally` owns an
    indicator; the indicator then measures the call, not the work. Because the chart build
    that follows is synchronous and can freeze the page, `fetchData` also yields one frame
    (`requestAnimationFrame` + `setTimeout`) after naming the step, or the last thing on
    screen during the freeze is a stalled percentage.
  - **A fetch with no indicator is a decision, not an oversight — and some are correct.**
    Leave silent: background polls (`/ai/status`), optimistic preference writes
    (`/ai/settings`), `beforeunload` beacons (`/drive/sync`), decorative enrichment with a
    graceful fallback (`/api/release-info`), memoised leaf helpers whose callers already
    show something (`fetchCalibrationJsonContent`), and the generic `fetchJSON` wrapper.
    Everything a user *starts by clicking* and then waits on gets one of the three.
    **Anti-pattern**: adding an indicator to a leaf helper — its callers already own the
    wait, and a memoised call would flash a placeholder for a cache hit.
- **Point-mode reference unit**: the "Set reference point to export" input (`#exp-json-time-value`) is entered in the currently-selected `#time-unit`; its label and value rescale whenever `#time-unit` changes (`refreshExpTimeValueForUnit` in `init.js`). Estimates use the selected unit, but **exports always convert the reference point to minutes** (`generatePointData` in `data-handling.js`) so calibration files stay in minutes (`TimeUnit: minute`).

### 2.8 Security & Production

- `ProxyFix` is applied for HTTPS behind Heroku's proxy.
- Session cookies are configured: `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_HTTPONLY=True`.
- Max upload size: 16MB (`MAX_CONTENT_LENGTH`).
- CSV content is validated against strict regex patterns before saving.
- JSON content is validated as parseable before saving.
- File names are sanitized with `werkzeug.utils.secure_filename`.
- `measMode` parameter in `/export_data` must be validated as `kinetics` or `point` before use.
- `mode` parameter in `/get_json_content` must be validated as `kinetics` or `point`.
- `threshold_val` in `/export_cal_coefs` must be converted with try/except and clamped to [0, 1].
- `/export_report_excel` enforces `len(items) <= 500` and `len(title) <= 255`.

**The origin allowlist is server-configured, and it covers the fallback host.**
`src/security.py` builds it from `APP_BASE_URL` + `APP_FALLBACK_URLS` +
`EXTRA_ALLOWED_ORIGINS`, and (when dyno metadata is on) `HEROKU_APP_DEFAULT_DOMAIN`.
- `APP_BASE_URL` is a **branded custom domain** — DNS + CDN + TLS in front of this
  dyno, every layer of which can fail while the app is healthy. When it does, the
  platform hostname (`*.herokuapp.com`) is still serving this same app and is
  where users get sent. Its hostname must therefore be on the allowlist, or the
  fallback renders but cannot be used: every sign-in and form POST 403s here.
  Set `APP_FALLBACK_URLS` to that address in production.
- The **desktop client is not affected either way** — it sends no Origin, so its
  token-authenticated calls (`/api/activate`, `/api/license/check`,
  `/api/license/release`, `/ai/proxy/chat`, `/api/download`, `/api/version`) pass
  the guard on any hostname. That is why the desktop can fail over to the
  platform hostname with no server change at all (main branch, `Rule.md §2.17`).
- **Anti-pattern**: adding the request `Host` (or a blanket `*.herokuapp.com`
  match) to the allowlist. Host is attacker-controlled; these values are not,
  because they come from this deployment's own configuration.
**Anything we link back to ourselves with follows the request host — from the
allowlist, never from the Host header.** `security.request_base_url()` returns
the current request's scheme+host **if that hostname is one we serve**, else
`APP_BASE_URL`. `request_callback_url(path)` appends a path for OAuth. Users of
it: `oauth_routes._base_url()` (Google/GitHub sign-in), `account_routes._link_base()`
(verification + password-reset mail), `google_drive_service.create_oauth_flow()`.
- **Why not `APP_BASE_URL` everywhere**: it names the branded domain, so a user
  who reached us on the fallback host gets an OAuth bounce and e-mail links
  pointing at a name that is down — at the one moment the fallback mattered.
- **Why the allowlist is load-bearing, not decoration**: `request.host` is
  **client-controlled**. `ProxyFix(x_host=1)` trusts `X-Forwarded-Host`, which
  the router fills from the client's own `Host`. Using it unchecked in a
  password-reset link is textbook **host-header injection**: the attacker asks
  for a reset on a victim's address with `Host: attacker.example`, and the victim
  gets a genuine e-mail whose link carries the reset token to the attacker. An
  unrecognised host must fall back to `APP_BASE_URL` — safe, merely inconvenient.
  **Anti-pattern**: "just use `request.host`", or `url_for(..., _external=True)`
  in mail, which has the same flaw.
- **The OAuth triple has to agree**: the `redirect_uri` sent at authorize time,
  the one sent at token exchange, and what is registered with the provider. The
  first two agree by construction (the callback lands on the host the flow
  started on, so both computations see the same request). The third is **manual
  configuration** — every host this can return must be registered with the
  provider — and it is what makes the two providers asymmetric:
  - **Google** registers several redirect URIs, so its `redirect_uri` follows the
    request host. Registered: the branded and fallback callbacks for both
    `/auth/oauth/google/callback` (sign-in) and `/auth/google/callback` (Drive).
  - **GitHub's OAuth app holds one authorisation callback URL**, so
    `_github_base_url()` stays pinned to `GITHUB_OAUTH_BASE_URL` (default
    `APP_BASE_URL`) and never follows the request.
- **A pinned provider must refuse to start from anywhere else, not just fail
  later.** With GitHub pinned, a flow begun on the fallback host is doomed *even
  when every host is up*: `oauth_state` lives in the session cookie, cookies are
  host-scoped, and the callback lands on the branded host with a different jar —
  so the state check fails after a full round trip through GitHub.
  `oauth_github_start()` therefore refuses up front and names the host that
  works, and `github_signin_available()` gates the button out of `login.html` /
  `signup.html`. **Anti-pattern**: rendering a sign-in control that cannot
  succeed from the host it is being rendered on.
- **Admin-triggered mail keeps `APP_BASE_URL`** (licence revoked, account
  banned): it is addressed to the account owner, not to whoever is driving the
  admin console, so the canonical branded name is correct there.
- Sessions and logout need none of this — the cookie is host-scoped, so signing
  in and out on the fallback host works on its own once the origin guard allows
  the host (above).

### 2.9 Frontend XSS Prevention

- **Never** insert server-provided strings (filenames, subject names, JSON keys/values) into `innerHTML` or HTML attribute values via template literals without escaping.
- Use `_escHtml(s)` (defined in `navigation.js` and `data-handling.js`) for HTML text context and HTML attribute values.
- Use `JSON.stringify(value)` to pass string arguments inside `onclick="func(…)"` attributes — this is the safe pattern for table row buttons.
- Prefer `textContent` over `innerHTML` whenever the content is plain text (no intentional markup).
- Build complex DOM nodes with `document.createElement` + `textContent` instead of `innerHTML` template strings when user-controlled data is involved.

---

### 2.10 AI Assistant — Groq Cloud LLM

- The AI assistant uses **Groq API** (`https://api.groq.com`) — never Ollama or a local LLM.
- `GROQ_API_KEY` and `AI_MODEL` are read from environment variables via `src/config.py` (`Config.GROQ_API_KEY`, `Config.AI_MODEL`).
- Default model: `openai/gpt-oss-20b` (GPT-OSS reasoning model). Override via `AI_MODEL` env var on Heroku.
- **The model is ours to choose — `/ai/proxy/chat` ignores `data['model']`.** Honouring it meant every installed desktop build pinned whatever model id was current when it was frozen, so Groq retiring `llama-3.1-8b-instant` 404'd (`model_not_found`) the chat in copies that can no longer be edited. Reading `Config.AI_MODEL` instead lets one Heroku config var move every client, shipped or not, onto a live model. The desktop side stopped sending the key as well (main `Rule.md` §2.13), but the server rule is the one that rescues builds already in the field. **Anti-pattern**: do not let a caller pick the model that our Groq key pays for.
  - GPT-OSS models spend completion tokens on reasoning; `_groq_chat` sets `reasoning_effort="low"` for any `openai/gpt-oss*` model. Every model gets the one `_MAX_COMPLETION_TOKENS = 2048` budget (there is no per-model override any more), and a `finish_reason == "length"` answer is flagged with `_TRUNCATION_NOTICE`. Reasoning is returned in a separate field, not `content`.
- Settings are stored **per-session** in Flask `session['ai_settings']` via `src/ai_settings.py`. No file-based persistence.
- The AI blueprint is `ai_bp` in `src/routes/ai_routes.py`, mounted at `/ai/*`.
- Routes: `GET /ai/status`, `GET|POST /ai/settings`, `POST /ai/chat`, `POST /ai/proxy/chat` (desktop builds, licence-token auth), `GET /ai/guides`.
- **No pull_model/pull_status routes** — model management is handled by Groq, not the app.
- Chat uses **SSE streaming** (`text/event-stream`). The generator in `chat_stream()` emits `{"type": "chunk"|"guide"|"pending"|"error", ...}` events (the web client also handles `clear`); the final event is `[DONE]`.
- Tool execution uses `user_data` from `get_user_data()` (in-memory per-session CSV/JSON store). Never reads from local filesystem.
- `get_hardware_status` tool is **absent** from the online TOOLS list (no hardware in online).
- `trigger_custom_steps` valid CSS IDs match the online UI — no hardware IDs (`#run-script-btn`, `#log-hid-data`, etc.).
- `guide_training.json` and `guide_translations/*.json` are committed to the repo (gitignored by `*.json`, but explicitly un-ignored in `.gitignore`).
- Conversation history is **client-side only** (`AI.messages` array in `ai-chat.js`).
- Supported languages: `en`, `vi`, `zh`, `fr`, `ja`, `ru`, `ko` — one list, `ai_settings.SUPPORTED_LANGUAGES` (`ai_assistant.VALID_LANGS` is derived from it). Active language sent per request as `language`; both chat routes validate it (unknown → `en`), and the guide cache is keyed on the validated value only. A first-time visitor's chat language is seeded from the page language (`/ai/status` → `language_chosen`), and the widget loads guides only after the language is known. A session that already stores a non-default `preferred_languages` (saved before the flag existed) counts as chosen and keeps its language.
- **Chat-loop contract (both routes, work-list A1).** `_groq_chat` budget is `_MAX_COMPLETION_TOKENS = 2048`. A `tool_use_failed` 400 and an empty reply are each retried once with tools off; a `finish_reason == "length"` answer is followed by `_TRUNCATION_NOTICE` (7 languages). The client only ever sees a code from `STABLE_ERROR_CODES` (`api_key_invalid`, `rate_limit`, `tool_call_failed`, `max_iterations`, `groq_not_installed`, `service_unavailable`, `upstream_error`); raw upstream exception text is logged server-side and never streamed. **Anti-pattern**: do not forward `str(e)` to a client — old desktop builds render unknown codes as `⚠ <code>`, which is fine for `upstream_error` and a leak for anything else.
- **`/ai/proxy/chat` serves every activated desktop build — shipped builds included, so every rule here must work for all 1.5.x payload shapes** (with/without `ui_context.pending`, with/without `client_grounding`, with/without `trigger_custom_steps` in its tools):
  - **Local-only tools are refused (A2).** `get_app_context`, `read_csv_file`, `read_calibration_file` and `get_hardware_status` answer `{"error": "not_available_via_proxy", …}` for every proxied call, and the proxy never loads the account's cloud store. Keyed on the route (`proxy_request=True`), never on a client flag: old builds keep sending these tools and this refusal is their only protection. **Anti-pattern**: answering a desktop's "which files do I have" from the website's per-account store.
  - **Fast paths (A3).** A grounded request that carries `ui_context.pending` (main ≥ 1.5.7) skips greeting / out-of-scope / report clarification — the desktop already ran them locally. A grounded request without the key (pre-1.5.7) keeps only the report fast path. Server-side guide matching is always skipped for grounded calls.
  - **Input validation (A5).** Messages are filtered to `{role: user|assistant, content: str}`, newest 24. Only the **current** (last) message can make the request 413 (> 8,000 chars); over-long older history is cut to 8,000 chars and the oldest turns are dropped until the total is ≤ 24,000 — one long assistant reply must not lock the conversation, and old desktop builds without client caps must not see an outage; `client_grounding.system_prompt` and `help_docs` ≤ 16 KB each (413). Client tools pass only through `_GROUNDED_TOOL_ALLOWLIST`. `_SERVER_SCOPE_RULE` is appended after every client prompt. `tests/fixtures/main_1_5_11_proxy_payload.json` is a captured main 1.5.11 payload that must keep passing.
  - **Rate limit (A4).** `main.py` applies `ProxyFix(**rate_limit.PROXY_FIX_KWARGS)` (`x_for=1`, so `remote_addr` is the client, not the Heroku router); the proxy limiter keys on the verified licence `sub` (IP fallback), and the AI blueprint answers 429 as JSON `{"status": "failure", "code": "rate_limit"}`.
- **Web guide matcher (A6/A7/A14/A16).** Scoring helpers (`_phrase_hit`, `_score_keyword`, `_score_guide_keywords`, `_condition_excludes`, `_mode_bonus`) and the launch gate (`_has_nav_intent`, `_is_conceptual`, `_is_tour_request`, `_should_launch_guide`) are **identical to main's** — change them on both branches. Phrase hits sit on word boundaries (≥ 4 chars, ≥ 2 for CJK, not a stop-word; a hyphenated `un-/re-/de-` prefix never matches). The boundary is a **non-CJK** word character: a Latin term written against CJK/kana ("切换到kinetics模式", "pointモード") must still hit — plain `\w` broke that once. A CJK keyword weighs about one word per two characters. Each distinct word set counts once per guide (ties go to more matching keywords); the mode bonus needs a baseline ≥ `_NAV_LAUNCH_SCORE`. Ranking puts a guide whose keyword IS the whole query first (then score, then hit count). Launch rule: nav phrasing + a solid hit, or a tour request, or the WHOLE query is one of the guide's keywords (`_HIT_EXACT`: "导出数据", "combine csv files", a bare mode name), or a strong multi-word match without nav phrasing. Conceptual questions always reach the model. **Exact-keyword launches are strict (fix round 2):** `_HIT_EXACT` compares tokens with only `_EXACT_FILLER` removed (how/to/the/a/an/i/me/do/please, the take-me verbs go/get/find/show/see/open, and articles) — negations and pronouns count, so "not export" / "my data" are not the keyword "export" / "data". A keyword that is one generic word (`_GENERIC_EXACT`: data, source, r2, log, mode, 데이터 …) or is listed under 3+ guide families in that language (`_shared_exact_keys`; mode variants such as concentration_calc_* are one family; e.g. vi "đường chuẩn") carries no launch evidence; mode names (`_MODE_WORDS`) are never vague. Without how-to phrasing a negated query (`_has_negation`, all 7 languages) carries no launch evidence unless the matched keyword is itself negated ("no popup", "不要弹窗"). **Known limit (N5, decision D3):** there is no "problem report" detector, so a statement that contains a guide's multi-word / CJK phrase ("导出数据失败了", "my export data has a problem") still launches that guide, in every language. Keyword regexes/features/vocabulary are compiled and cached once (`_keyword_regex`, `_keyword_features`, `_vocabulary_of`) — **anti-pattern**: building a regex string per keyword per query (re's 512-entry cache thrashes; a match took 6x longer). `tests/test_ai_guide_routing.py` sweeps the whole corpus for the MATCH (strict-xfail `KNOWN_MISROUTES`) **and** for the LAUNCH (`LAUNCH_PROBES`, own-query launch-rate floor); a latency guard sits in `test_ai_guide_matching.py`. Mode-switch steps are structural (`requires_mode` + `_MODE_SWITCH_STEP`), never inferred from step prose. The out-of-scope filter matches from a word start.
- **Report clarification (A8).** The quick/full question emits `{"type": "pending", "pending": "report_type"}`; `ai-chat.js` echoes it as `ui_context.pending` (always sends the key). Prose matching of the question is only a fallback for clients without the key. It is not asked for report-management or conceptual questions (shared rule with main). Report walkthroughs are guides loaded by id (`report_quick`, `report_quick_from_report`, `report_full_from_data`, `report_full_in_report`) — never Python step constants.
- **LLM-written steps (A10).** An error from `trigger_custom_steps` / `trigger_guide` goes back to the model and is never emitted as a guide; web calls whitelist targets (`_custom_step_whitelist` = the tool's ID list + this app's guide targets + every element id written literally in `templates/` and `static/script/`, derived from the source by `_source_element_ids`; credential, destructive and licence controls are excluded from the whole whitelist by `_DENIED_TARGETS` + `_DENIED_TARGET_RE` (e.g. `#password`, `#swal-delete-pw`, `#token-display`, `#shutdown-btn`, `#activateBtn`, `#okapi-ai-token-input`) — **anti-pattern**: never let an LLM-written step spotlight a credential or destructive control, so invented ids are still rejected); proxied calls only need `#id` (their ids belong to the desktop UI). Unknown workflows return `unknown_workflow`. `user-guide.js` skips an invalid selector and ends the guide when the last target never appears.
- **Grounding text (A11/A12/B16).** `_HELP_DOCS` states the forms `math_ops.py` fits (pinned numerically in `tests/test_ai_tools.py`). Every language's system prompt is translated prose + the one English `_PROMPT_RULES` block (ids, domain sections, Turn rules, DATA SAFETY) — `tests/test_ai_prompts.py` pins the parity. File contents come back as `untrusted_file_content`.
- **Guide targets and overlays (A9/A15).** Every static guide target must exist in `templates/` or `static/script/` (`tests/test_guide_targets.py`). Overlay steps may be `{target, description, title}` (matched by target) or legacy strings (by position); new or re-translated entries use the keyed form.
- `ai-chat.js` in production is built to `static/dist/ai-chat.min.js` via `npm run build`. `OkapiAI` is in `MANUAL_RESERVED_NAMES` in `build.js`.

---

### 2.11 Concentration Unit + CSV↔JSON Identity

- **Concentration unit (`# ConcenUnit`)**: the unit a concentration is expressed in — the `# Concentration:` metadata of a raw timeseries CSV, or the `Concentration` column of a calibration CSV. One of **`ng/µL`, `nM`, `%`** (`CONCEN_UNITS` in `src/file_path.py`, the single source of truth — injected into the page as the `CONCEN_UNITS` JS const). A **label only**: switching units never converts the recorded numbers. `get_concen_unit(meta)` returns the documented default `ng/µL` when the line is absent.
- **No persisted default, no migration** (online specifics): the `#concen-unit` dropdown (Data Display section) defaults to `ng/µL` each session and reflects the loaded file (`getMetaConcenUnit`/`syncConcenUnitDropdown`); there is no settings store. Storage is in-memory (`user_data['csv']`/`['json'][mode]`), so an absent `ConcenUnit` is simply **defaulted at read time** — the line is materialized only when the user edits the unit (Edit-File metadata **dropdown**, built from `CONCEN_UNITS`) or exports. **Do not** back-fill stored content on `get_csv`/`get_json_cal` (avoids needless Firebase/Drive writes).
- **Export**: `data_routes.export_data` reads `concenUnit` and threads it into `write_metadata` + `is_metadata_consistent`; appending a different unit to an existing calibration file is rejected with a `Concentration unit mismatch` error. `export_cal_coefs` records the curve's identity — `for_meas` (Measurement), `meas_unit`, `concen_unit` — into the JSON.
- **CSV↔JSON identity matching**: a measurement CSV is paired with a calibration JSON only when they share **Measurement + Unit + ConcenUnit**. `file_path.build_csv_identity_from_store` / `build_json_identity_from_store` return `{name: {measurement, unit, concen_unit}}` from the in-memory stores; `get_csv` / `get_json_cal` return them as `files_identity` and the index injects `FILE_IDENTITY` / `CAL_JSON_IDENTITY`. Both tables show an inline `Measurement·Unit·ConcenUnit` badge (`.file-identity`); when a counterpart is selected, a non-matching row's **Select button is disabled** (`navigation.js` `_selectDisableAttrs`), and `selectFile` raises an explicit mismatch error as a backstop. Measurement/Unit are **wildcards when absent** on either side (legacy JSONs stay usable; `NONE`/blank normalized via `_norm_identity_value` / `_normIdent`); ConcenUnit is always enforced (absent ⇒ ng/µL).
- Report derived-concentration lines and the calibrate chart axis use the actual unit (`_reportConcenUnit` / `getMetaConcenUnit`), not a hardcoded `ng/µL`.
- **Build note**: all of the above edits live in `static/script/` source; run `npm run build` so `static/dist/*.min.js` (+ `style.min.css`) reflect them before a production deploy.

---

### 2.12 Point-Mode Turn Axis

- **A raw series file's X column is `Timestamp` (elapsed seconds) *or* `Turn`** — a 1,2,3… measurement index for point mode. A Turn file has header `Turn,Value:1[,Value:2,…]` and **never** carries a Timestamp column. Schema `CSV_SCHEMA_TIMESERIES_TURN` (`src/file_path.py`); `timeseries_x_column(header)` names the X column of either.
- **The read path renames, it does not branch**: `/get_data` renames the `Turn` key → `Timestamp` on read and returns `x_axis: 'turn'`. The entire `"Timestamp"`-keyed client pipeline (plot, value-at-point, reports) is therefore unchanged; the client stores `AppState.xAxis` and only relabels the chart axis / reference input. **Never** back-fill or rewrite stored content on a read.
- **Turn calibration**: a Turn file has no time, so each recorded Turn is treated as one concentration standard. A point-mode Turn file hides the time-point controls and shows a per-Turn concentration table (`applyTurnCalUI` / `renderTurnCalTable` / `exportTurnCal` in `data-handling.js`), exporting a `Concentration,Value` calibration CSV (schema `CSV_SCHEMA_POINT_CAL_TURN`, **no TimePoint**). The resulting calibration JSON records `x_axis: 'turn'` and omits `time`/`time-unit`; deriving reads each Turn's value straight through the fit (`processTurnDerive`).
- **Turn and time never mix.** `/export_data` refuses to append turn rows to a time-based point calibration table (and vice versa) — the column counts differ. Identity gains an **axis** dimension: a Turn data file pairs only with a turn calibration and a Timestamp file only with a time calibration (`build_csv_identity_from_store` / `build_json_identity_from_store` → `axis`; `identityMatch` in `navigation.js`). `merge_csv_contents` joins Turn files on the `Turn` index; mixing Turn + Timestamp files fails.
- **Converter**: **Timestamps → Turns** in the CSV editor (`POST /convert_timestamp_to_turn`) rewrites a stored timeseries file in place — header `Timestamp` → `Turn`, first cell → 1-based index. One-way and destructive (the recorded times are dropped); a Turn file or a calibration file is rejected.
- **Point-mode display**: no kinetics analysis table and no Save Linearity button (point reads a value at a point, it does not fit a slope); the Expand/Collapse-all-analyses toggle and the Display range (From/To) are hidden — only the Time unit selector (`#time-unit-row`) survives, and even that is hidden for a Turn file. `filteredByRangeValue` never clips in point mode, and `extractColumnAndConvert` never applies the seconds→time-unit rescale to a Turn index.
- **Replicate standards are averaged.** A point calibration fit averages values sharing a concentration so each standard is weighted once (`averageDuplicates` in the live display, `averagePointsByConcentration` in reports), and the value spread renders as min–max error bars. Keep the live fit, the report fit and the exported coefficients consistent.
- Keep the three schema mirrors in lockstep: backend `_SCHEMA_VALIDATORS` (`src/validators.py`), the editor `patternSets` (`static/script/edit-file.js`), and `detect_csv_schema`.

---

### 2.13 Community Content — Reviews and Publication Reference

- **Both lists are curated repo files**, read by `src/community.py`: `testimonials.json` (reviews banner) and `publications.json` (citation block + publication list). They are gitignored by `*.json` but explicitly un-ignored in `.gitignore`. Content is injected server-side by `main.py` `index()` (`testimonials`, `publication_ref`) so neither section costs a round-trip; `GET /api/testimonials` and `GET /api/publications` expose the same data for any other consumer.
- **Nothing a visitor sends is ever published.** `POST /api/testimonials/submit` validates the payload and **emails it to the admin** (`REVIEW_ADMIN_EMAIL`, falling back to `SMTP_USER`); the admin confirms consent with the author and adds the entry to `testimonials.json` by hand. There is no moderation table and no write path from the web to either file — do not add one. The submission mail is **plain text only** (the body is visitor-supplied and must never be rendered as HTML), and `Reply-To` is the reviewer so consent can be confirmed in one click.
- The endpoint sends real mail and needs no account, so it is rate-limited (`REVIEW_SUBMIT_LIMIT`, `src/rate_limit.py`). An SMTP failure returns a generic 503 — never leak the underlying error to the caller.
- **Never fabricate a review or a publication.** Only add an entry whose author actually said it and consented to the attribution; an empty list is the correct state until then (both sections render an invitation instead).
- UI: the reviews banner (`#reviews-banner`) is a collapsible strip **above** the app, collapsed by default with the choice persisted in `localStorage` (`reviews-banner-collapsed`); the Publication reference (`#publication-section`) sits at the page bottom, collapsed by default. Interaction lives in `static/script/community.js` (`toggleReviewsBanner`, `openReviewForm`, `copyCitation`) — all four public names are in `MANUAL_RESERVED_NAMES` in `build.js`.

---

### 2.14 UI Localization (i18n) — seven languages, language in the URL

- **The URL carries the language.** English lives at the bare path (`/terms`) and
  is the canonical URL; the other six live under a prefix (`/vi/terms`). Never
  make a bare URL render something other than English — a crawler or a cache
  would then see a page that changes under it. `src/i18n.py:init_app` mirrors the
  page rules under `/<any(vi,zh,fr,ja,ru,ko):lang>` after every blueprint is
  registered; a new indexable page must be added to `LOCALIZED_ENDPOINTS`.
- **The `ui_lang` cookie only remembers a preference.** It is read on `/` alone,
  to redirect a returning visitor, and written by `/set-language/<code>`, which
  the picker links to. Never key page content off it.
- **Link with `url_for`, never with a hard-coded path.** `inject_lang` puts the
  active language into every `url_for`, so `/terms` written by hand silently
  drops the visitor back to English.
- **Markup is translated server-side** with `{{ t('key') }}` / `{{ t_html('key') }}`
  (the latter only for catalog strings that carry inline markup). Strings the
  *browser* builds — Swal dialogs, chart labels — use `window.t('key', 'English')`
  from `static/script/i18n.js`; keep the English literal as the fallback there,
  and call it as `window.t` because `t` is a common local variable name.
- **Catalogs are `ui_translations/<lang>.json`**, flat key → string, English as
  the baseline. Adding a string means adding its key to **all seven** files in the
  same commit — `tests/test_i18n.py` fails on drift, on a lost `{placeholder}`,
  and on an empty value.
- **Technical terms stay English** in every catalog: mode names (kinetics, point,
  calibrate, report), units, Absorbance, maxRate, rSquared, CSV/JSON/Excel,
  regression names, and brand names.
- **A translated legal document is not a second original.** `legal_base.html`
  renders a governing-language notice on every non-English legal page, pointing
  at the English text. Do not remove it, and keep `legal/` prose and the catalog
  in step when either changes.

### 2.15 Accessibility — WCAG 2.2 Level AA is a published claim, not an aspiration

- **The claim is public and dated.** `/accessibility` (`templates/accessibility.html`,
  `main.py:accessibility`, versioned by `A11Y_VERSION` / `A11Y_EFFECTIVE`) states
  that the web app and the public pages are **partially conformant with WCAG 2.2
  Level AA** and lists, by name, everything that is not. Breaking a criterion
  does not just degrade the UI — it makes a published statement false. If you
  cannot fix a barrier, **add it to `a11y.limits.c*` with a workaround**; the
  test suite rejects a limitation that has no way round it.
- **Four files carry the primitives**, and they have to stay in step:
  `static/style.css` (web app), `static/landing.css` (landing + legal),
  `static/legal.css` (contact form), `templates/_a11y_head.html` (the account
  pages, which load none of the above). Each has an
  `Accessibility (WCAG 2.2 Level AA)` block. Skip link, `.sr-only`,
  `:focus-visible`, reduced motion, forced colours, 24px targets.
- **Never remove a focus indicator.** `outline: none` is allowed only where a
  later `:focus-visible` rule replaces it. The rings are two-toned (dark core +
  light halo) so they clear 3:1 on either theme and over any button fill.
- **The 2.5.8 floor is a blunt instrument — keep its selector list short.**
  `min-width`/`min-height` beat `width`/`height` **at any specificity**, so
  `button, [role="button"], … { min-height: 24px; min-width: 24px }` cannot be
  reasoned about as an ordinary declaration: it silently wins over whatever size
  the design system set, from anywhere in the file. It has already broken two
  things — the 18px checkboxes and radios (fixed in `6abcf6e`) and every
  `<select>` in the app, which lost the `min-width: 150px` it is given near the
  top of the sheet because both rules are `(0,0,1)` and the accessibility block
  comes last. Before adding a selector to that rule, check whether the element
  already declares a size; if it does, meet the criterion on the element itself
  (or through the **spacing exception**) rather than growing it from the bottom
  of the file. An accessibility rule that outranks the design system is not
  accessible, it is just louder.
- **A click handler belongs on a control.** No `onclick` on a `<div>`, an
  `<img>` or a heading — it is unreachable by keyboard and has no role. The
  collapsible section headings are `<h2><button class="folder-section-toggle">`;
  `toggleFolderList(collapseId, chevronId, trigger)` keeps `aria-expanded` in
  step, and the chevron is `aria-hidden` decoration.
- **A collapsed panel must leave the tab order.** `.section-collapse.collapsed`
  carries `visibility: hidden` (delayed one transition) as well as
  `max-height: 0`; without it the keyboard walks into invisible buttons.
- **Announce, don't just render.** `announce()` (polite) and `announceAlert()`
  (assertive) in `short-hands.js` write into the two live regions that ship in
  `index.html`. They must exist from first paint and must never be
  `display: none`. `$showText` announces every error it displays.
- **A `<canvas>` is not content.** `generateChart` calls `buildChartDataTable`
  (`static/script/a11y.js`), which names the canvas and publishes the same
  numbers as a real table, built only when the reader opens it. Do not add a
  chart without one.
- **Table renderers rebuild their own semantics.** `updateFileTable`,
  `updateJSONTable` and `updateReportTable` replace the whole `<table>` with
  `innerHTML`, which discards the caption, `<thead>` and `scope` the template
  shipped — `_tableHead()` puts them back, and `_rowBtnLabel()` gives each row
  button a name that says which row it acts on.
- **New user-facing string ⇒ seven catalogs** (§2.14 applies unchanged). The
  accessibility statement is a legal document: it renders on `legal_base.html`,
  appears in `LOCALIZED_ENDPOINTS`, and carries the governing-language notice.
- **`tests/test_accessibility.py` is the guard.** It is static analysis over
  the templates, stylesheets and scripts — it catches a deleted label, a lost
  skip link, an unlabelled icon button, a table that lost its `scope`. It
  cannot replace a screen reader, and the statement says as much: automated
  checks are a floor, roughly a third of what matters.

---

## 3. Autonomous Documentation Updates

- **Self-Reflection Request**: Upon completing any significant task, feature implementation, or architectural change before returning control to the user, you **MUST** evaluate if updates are required for `Rule.md` or `easyokapi-knowledge/EASY OKAPI.md`.
- **Functional updates**: If your changes introduce new files, routes, dependencies, or alter the architectural flow, you MUST proactively edit `easyokapi-knowledge/EASY OKAPI.md`.
- **Behavioral updates**: If your task establishes new strict coding patterns, behavioral constraints, or anti-patterns, you MUST proactively edit `Rule.md`.

# Vaidyx core map: what the Tumour Board depends on (18 Oct 2026, Explore agent; verified points marked)

Repo /home/bharath.tangella/vaidyx/Vaidyx, branch the-ui. FastAPI 0.142, Starlette 1.7, uvicorn 0.54, Python 3.10 in /data/vaidyx/venv/app.

## 1. core/auth.py (AuthManager)
- User store data/auth.json: {"users": {username: {password_hash (bcrypt), created, is_admin, privileges, [totp_secret, totp_enabled, totp_backup_codes, must_change_password (added 18 Oct)]}}, "signup_enabled"?}. 14 users today, one admin "admin". Usernames lower-cased.
- Privileges: can_use_agent, can_use_browser, can_use_bash (off by default), can_use_documents, can_use_research, can_generate_images, can_manage_memory, max_messages_per_day, allowed_models, block_all_models. Admins get the shell tool.
- Reserved usernames: internal-tool, api, demo, system.
- Sessions data/sessions.json {token: {username, expiry}}; token_hex(32); TOKEN_TTL 7 days fixed (no sliding). validate_token / get_username_for_token check expiry and that the user exists. revoke_token, revoke_user_sessions(u, except_token).
- TOTP (pyotp): totp_enabled, totp_generate_secret, totp_get_provisioning_uri (issuer Vaidyx), totp_confirm_enable (8 backup codes), totp_verify (True when 2FA off), totp_disable.
- change_password(u, current, new) (min length 8 checked in the route; now clears must_change_password). ADDED 18 Oct: reset_password(u, new, must_change=True) (revokes sessions), must_change_password(u); status() includes must_change_password.
- set_admin never demotes the last admin. is_admin(u) read live; TB _roles() passes vaidyx_admin=is_admin(u) to org.roles (a Vaidyx admin is a TB admin). accounts.py refuses to place a Vaidyx admin.
- No lockout in AuthManager.

## 2. routes/auth_routes.py (/api/auth)
POST /setup (3 per 5 min per IP), POST /signup (only when enabled), POST /login {username, password, remember=true, totp_code?} (15 per min per IP; 401 Invalid credentials; 200 {ok:false, requires_totp:true} when a code is needed; sets cookie), POST /logout, GET /status {configured, authenticated, username, is_admin, privileges, signup_enabled, must_change_password}, GET /policy, POST /change-password {current_password, new_password} (then revokes other sessions), 2FA: /2fa/setup, /2fa/confirm, /2fa/disable, /2fa/status; admin: GET/POST/DELETE /users, PUT /users/{u}/privileges|rename|admin, PUT /open-signup; GET /features, /settings public (scrubbed).
- Cookie vaidyx_session, HttpOnly, SameSite=Lax, Path=/, Secure only with SECURE_COOKIES=true (not set). Max-Age 7 days when remember.
- CSRF: none (SameSite=Lax + JSON bodies + CORS). Other ports on the same host count as same site.
- Rate limiter src/rate_limiter.RateLimiter in memory per process keyed by client host (everyone is 127.0.0.1 behind the port forward).

## 3. Auth enforcement and headers
- AuthMiddleware lives in app.py lines ~254 to 470. Public: /api/auth/{setup,signup,login,logout,status,features,settings,integrations/presets}, /api/health, /api/version, /login; prefixes /static and (18 Oct) /tb-nik; webhook pattern; CORS preflights. Order: internal tool header (loopback only), LOCALHOST_BYPASS (off), not-configured, Bearer ody_ API tokens (current_user "api"), cookie. Unauthenticated: /api/... 401 JSON {"error": "Not authenticated"}; other paths 302 /login. Sets request.state.current_user, api_token=False.
- src/auth_helpers.require_user: used by TB _user/_roles; 403 for bearer tokens (cookie only).
- core/middleware.py: require_admin, is_cors_preflight, INTERNAL_TOOL_*, SecurityHeadersMiddleware. Headers: X-Content-Type-Options nosniff, Referrer-Policy no-referrer, Permissions-Policy (18 Oct) camera=(self), microphone=(self), geolocation=(); HSTS on https. Default CSP (18 Oct): default-src 'self'; script-src 'self' 'nonce-X' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self' ws://127.0.0.1:7880 http://127.0.0.1:7880; frame-src 'self' http://127.0.0.1:8042; frame-ancestors 'none'; X-Frame-Options DENY. No worker-src (falls back to script-src: blob: workers blocked).
- Limits: no global body cap; TB uploads read into memory, 413 above 60 MB; _RequestTimeoutMiddleware 504 after 45 s except /api/tb, /api/chat, /api/research, /api/upload; GZip above 1 KB except text/event-stream; CORS ALLOWED_ORIGINS default http://localhost,http://127.0.0.1 with credentials.
- Middleware order outermost first: Auth, SlowRequestLog, InteractiveActivity, RequestTimeout, SecurityHeaders, GZip, CORS. Auth 401/302 replies carry no security headers.

## 4. app.py
- Static mount /static -> <repo>/static via _RevalidatingStatic (no-cache on .js/.css/.html). TB router: setup_tumour_board_routes() prefix /api/tb, route_class _ModelErrorRoute (blocks disabled or unplaced users; model errors -> 502); starts a thread warming the guideline index.
- Page routes: /, /tb (static/tb/index.html), /tb-nik and /tb-nik/{path} (18 Oct; static/tb-nik/index.html), /login (static/login.html), others. serve_html_with_nonce replaces {{CSP_NONCE}}.
- Start-up lifespan: tumour_board.service.resume_after_restart() first, then other sweeps. Run: uvicorn.run(app, host 127.0.0.1, port 7000), one worker. Logs data/logs/app.log. Start script ~/vaidyx/start_vaidyx_app.sh (APP_BIND, APP_PORT; AUTH_ENABLED true).

## 5. WebSocket and SSE
- No WebSocket anywhere today. websockets 16.1 installed. All middlewares are BaseHTTPMiddleware and pass non-HTTP scopes through: a WebSocket route gets NO auth and no headers; it must read the vaidyx_session cookie, call auth_manager.get_username_for_token and check Origin itself.
- SSE: chat and research streams; TB agents stream NDJSON at POST /api/tb/cases/{id}/agents/{role}. PACS proxy GET|HEAD /api/tb/pacs/{path} (tumour_board/pacs.py) streams bytes to Orthanc/OHIF per user per study after POST /api/tb/cases/{id}/documents/{doc}/images grants access. tb.js polls /api/tb/jobs/{id} every 700 ms.

## 6. Models and ports
- tumour_board/serve_models.sh: reader Qwen3.5-4B 127.0.0.1:8101 (bf16, 16384 ctx, GPU 0.17), reasoner gemma-4-31B-it 127.0.0.1:8100 (bf16, 32768 ctx, GPU 0.70, n-gram speculative). config.py: TB_*_URL overrides, data/tumour_board/models.json.
- Ports: 7000 app, 7110 TB MCP, 7111 demo HIS MCP, 7130 mock HIS, 7131 e2e copy, 8042 Orthanc/OHIF, 7120 reserved, 7100/7101 public demo (never touch).

## 7. tb.js API use
- api(path, opts): fetch("/api/tb"+path, credentials same-origin); 401 -> location /login (lands on main chat after login, no next parameter). No CSRF header.
- Demo users (plain Vaidyx accounts; passwords in ~/vaidyx/.tb_v2_demo_logins, mode 600, never print): tb-root (root admin), tb-mdt (coordinator), tb-rad-admin, tb-rad-doc, tb-path-admin, tb-path-head, tb-breast-admin, tb-breast-doc, tb-medonc-doc, tb-gynonc-doc, tb-micro-doc, tb-pulmo-doc, tb-crs-doc. Placements in data/tumour_board/org.json.

## 8. Theme tokens (tb.css :root)
--primary #00c0b5 (fill only, never text), --primary-h #00ada3, --on-primary #0b1f24, --accent #009c94, --link #046483, --indigo #3e5cad; --tint #e6f3f7, --tint-2 #f2f9fb, --tint-line #b6dde4; --ink #1f2933, --body #3e4c59, --muted #52606d, --line #d9e2ec, --line-2 #c5d1dc, --bg #f5f7fa, --panel #fff; --ok #1e6b45/#e5f4ec, --warn #8a5300/#fdf1d8, --bad #b23a2f/#fbe9e6, --rev #5b3fc4/#efebff; body 15px Atkinson Hyperlegible; --mono JetBrains Mono; --radius 10px; --shadow 0 1px 2px rgba(16,42,67,.06), 0 4px 12px rgba(16,42,67,.05); modal 0 20px 50px rgba(16,42,67,.25). Light only. Guard tests: tumour_board/tests/test_theme.py and eval/contrast_check.py (token names in :root, 4.5:1, no color: var(--primary), self-hosted fonts, no em dashes in static/tb, wordmark /static/vaidyx-wordmark.svg).

## 9. Fonts
static/tb/fonts: Atkinson Hyperlegible Regular/Bold/Italic/BoldItalic woff2, JetBrains Mono Regular/Medium, OFL files, README.

## 10. Tests
- pytest testpaths tests (main app, 710 files). TB: python -m pytest tumour_board/tests -q (71 files; conftest sets TB_DATA_ROOT temp, fixtures TB-001..003). his_mock: pytest his_mock/tests -q.
- e2e: python -m tumour_board.eval.e2e_api --base http://127.0.0.1:7000 --password <pw> (logs in as admin; creates throw-away accounts; resets TB-001..003; TB-TEST; mock HIS copy on 7131). UI: LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib /data/vaidyx/venv/app/bin/python -m tumour_board.eval.ui_test --password <pw> (Playwright, 1600x1000 / 1024x768 / 390x844, shots data/tumour_board/ui_shots). Gate: tumour_board/eval/gate.sh <label> [--v2] [--skip-ui] [--skip-evals].

## Watch points
1. WebSocket routes skip all middleware: authenticate inside the handler. 2. (fixed 18 Oct) CSP/camera for LiveKit. 3. After 401 the old UI lands on the main chat. 4. Login limiter per IP; everyone is 127.0.0.1. 5. No CSRF token; /static public; no global body cap. 6. tb.js runAgent ignores HTTP errors.

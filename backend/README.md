# backend (Stage 2)
`abix_api.py` - standard-library-only HTTP API, runs inside the desktop container (see documentation/STAGE2.md).
Endpoints: `GET /api/health`, `/api/session`, `/api/connect`, `/api/settings`, `/api/wallpapers`, `/api/wallpaper/<id>`, `/api/auth/check` (Nginx only);
`POST /api/login`, `/api/logout`, `/api/lock`, `/api/unlock`, `/api/settings`, `/api/power`. All POSTs need `X-Abix: 1` and JSON.
Test: `python3 tests/unit/test_backend.py`.
Terminal and file services (Stage 3) will be added here later and are NOT implemented.

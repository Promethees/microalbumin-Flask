# EasyOKAPI Download Token — Concept & Flow

This document explains how an authenticated Easy OKAPI user obtains a **download token** and how that token is linked server-side to a **GitHub Personal Access Token (PAT)** to deliver a private source tarball. It is written for an AI agent that needs to understand, extend, or debug this mechanism.

---

## Overview

The application uses a **two-layer token architecture**:

| Layer | Token | Holder | Purpose |
|-------|-------|--------|---------|
| **User-facing** | EasyOKAPI download token (JWT) | Client (browser / installer) | Proves the user is an authenticated, verified account holder |
| **Server-side** | GitHub PAT (`GITHUB_PAT` env var) | Flask server only | Authenticates requests to the private GitHub API on the user's behalf |

The user never sees or touches the GitHub PAT. The JWT acts as a short-lived credential that authorises the server to proxy GitHub content to that specific user.

---

## Component Map

```
src/
  account.py              — User model (SQLAlchemy), password hashing, verification tokens
  routes/account_routes.py — HTTP endpoints: register, login, /api/account/token, /api/download
  download_service.py     — JWT mint/validate, GitHub tarball proxy
  email_service.py        — Verification and password-reset emails
  config.py               — Env-var wiring (SECRET_KEY, GITHUB_PAT, …)
templates/
  login.html              — Login form; displays token after sign-in
  index.html              — "Get Offline Version" section; "🔑 Get Download Token" button
```

---

## Step-by-Step Flow

### 1. Account Registration

**Endpoint:** `POST /api/account/register`  
**File:** `src/routes/account_routes.py:42`

The user submits `{ email, name, password }`. The server:
1. Creates a `User` row in SQLite / PostgreSQL (`src/account.py`).
2. Hashes the password with **bcrypt** (`account.py:24`).
3. Generates a `secrets.token_urlsafe(32)` verification token, valid for 24 hours (`account.py:37`).
4. Sends a verification email containing `GET /api/account/verify/<token>` (`email_service.py:20`).

The user cannot download anything until `is_verified = True`.

---

### 2. Email Verification

**Endpoint:** `GET /api/account/verify/<token>`  
**File:** `src/routes/account_routes.py:76`

Clicking the link in the email sets `user.is_verified = True` and nullifies the one-use verification token. The user may now log in.

---

### 3. Login — EasyOKAPI Download Token is Minted

**Endpoint:** `POST /api/account/login`  
**File:** `src/routes/account_routes.py:143`

On successful password check and verified status:
1. Flask writes `account_user_id`, `account_user_name`, `account_user_email` to the **server-side session** (persistent, 30-day lifetime).
2. Calls `generate_download_token(user.id, user.email)` from `download_service.py`.
3. Returns `{ download_token, expires_in: 1800, user: {…} }` in the JSON response.

The login page (`templates/login.html`) receives this response and forwards the user to `/` (the main app). The token is available in `data.download_token` in JavaScript but is not persisted client-side beyond this moment.

---

### 4. The EasyOKAPI Download Token (JWT)

**File:** `src/download_service.py:11`

```python
_DOWNLOAD_PURPOSE = 'app_download'
_TOKEN_TTL = 30 * 60  # 30 minutes

def generate_download_token(user_id: int, email: str) -> str:
    secret = os.environ.get('SECRET_KEY', 'change-me')
    payload = {
        'sub':     user_id,           # database PK — identifies the user
        'email':   email,
        'purpose': 'app_download',    # scope guard — rejects tokens from other flows
        'iat':     int(time.time()),
        'exp':     int(time.time()) + 1800,
    }
    return jwt.encode(payload, secret, algorithm='HS256')
```

**Properties:**
- Algorithm: **HS256** (HMAC-SHA256), signed with `SECRET_KEY`.
- Lifespan: **30 minutes** (`exp` claim).
- Scope-locked: `purpose = 'app_download'` prevents tokens from other sub-systems being reused here.
- Stateless: no database row is created; validation is purely cryptographic.

---

### 5. Refreshing the Token from the Main App

**Endpoint:** `POST /api/account/token`  
**File:** `src/routes/account_routes.py:198`

A logged-in user (session contains `account_user_id`) can click **"🔑 Get Download Token"** in the sidebar. The browser calls this endpoint with no body; the session cookie proves identity. The server returns a fresh 30-minute JWT. The UI (see `index.html:605`) displays it in a SweetAlert modal with a **Copy** button.

This endpoint is also intended for programmatic use by the **offline installer**: the installer can POST to `/api/account/token` using the session cookie (or a stored token) to get a fresh JWT before calling `/api/download`.

---

### 6. Downloading the Source — The GitHub PAT Link

**Endpoint:** `GET /api/download?token=<jwt>`  
**File:** `src/routes/account_routes.py:266`

This is where the EasyOKAPI token is exchanged for real GitHub content:

```
Client                      Flask server                    GitHub API
  │                               │                               │
  │── GET /api/download?token=JWT ──>│                               │
  │                               │ validate_download_token(JWT)  │
  │                               │ (HS256 check + purpose check) │
  │                               │── GET /repos/.../tarball/<tag> ──>│
  │                               │   Authorization: Bearer GITHUB_PAT │
  │                               │<── 302 → tarball stream ──────────│
  │<── streaming .tar.gz ─────────│                               │
```

1. **Token validation** (`download_service.py:23`): decodes and verifies the JWT, checks `purpose == 'app_download'`, raises `jwt.InvalidTokenError` on any failure.
2. **User lookup**: fetches the `User` row by `payload['sub']`; verifies `is_verified` is still `True`.
3. **GitHub API call** (`download_service.py:32`): constructs the tarball URL, where the tag is the latest published GitHub Release (resolved via `get_latest_release_tag()`):
   ```
   https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/tarball/{release_tag}
   ```
   and adds the server's PAT in the `Authorization: Bearer <GITHUB_PAT>` header.
4. **Streams** the response back to the client with `Content-Disposition: attachment`.
5. Records `user.last_download = datetime.utcnow()` for audit purposes.

The **GitHub PAT** (`GITHUB_PAT` env var, also checked as `GITHUB_TOKEN`) is a classic or fine-grained token with at minimum **`repo` read** scope on the `Promethees/microalbumin-Flask` repository. It never leaves the server.

---

### 7. Environment Variables

| Variable | Where used | Description |
|----------|-----------|-------------|
| `SECRET_KEY` | `config.py`, `download_service.py` | HMAC secret for signing JWTs |
| `GITHUB_PAT` | `download_service.py`, `config.py` | GitHub Personal Access Token with repo read access |
| `GITHUB_TOKEN` | `main.py`, `config.py` | Fallback alias for `GITHUB_PAT` (used for the GitHub Release lookup) |
| `GITHUB_OWNER` | `download_service.py` | GitHub user/org owning the repo (default: `Promethees`) |
| `GITHUB_REPO` | `download_service.py` | Repository name (default: `microalbumin-Flask`) |
| `DATABASE_URL` | `config.py` | SQLAlchemy DB URI (SQLite default, PostgreSQL in prod) |
| `APP_BASE_URL` | `account_routes.py`, `email_service.py` | Public URL used in email links |

---

## Security Properties

- **Token scoping**: the `purpose` claim ensures a password-reset token or any other JWT cannot be used to trigger a download.
- **Short TTL**: 30-minute expiry limits the window if a token is intercepted.
- **Server-side PAT isolation**: the GitHub PAT never reaches the client. Users authenticate with the EasyOKAPI JWT; the server performs GitHub API calls on their behalf.
- **Email verification gate**: even a valid JWT is rejected if `user.is_verified` is `False` at download time.
- **Stateless validation**: no download-token table exists; revocation relies on expiry or `SECRET_KEY` rotation.

---

## Sequence Diagram (Full Flow)

```
User (browser/installer)     Flask / account_routes.py     GitHub API
        │                             │                         │
  [register]──POST /api/account/register──>│                         │
        │<──── 201 {message} ─────────│                         │
        │                             │                         │
  [verify email link]                 │                         │
        │──GET /api/account/verify/<tok>──>│                    │
        │<──── 200 (verified) ────────│                         │
        │                             │                         │
  [login]──POST /api/account/login──>│                         │
        │<── 200 {download_token, …} ─│  (session cookie set)  │
        │                             │                         │
  [get fresh token at any time]        │                         │
        │──POST /api/account/token───>│                         │
        │<── 200 {download_token} ────│                         │
        │                             │                         │
  [download]──GET /api/download?token=JWT──>│                   │
        │          validate JWT       │                         │
        │          lookup user        │                         │
        │                             │──GET tarball (Bearer GITHUB_PAT)──>│
        │                             │<── 200 streaming .tar.gz ──────────│
        │<── streaming .tar.gz ───────│                         │
        │                             │  user.last_download=now │
```

---

## Key Files Quick Reference

| File | Lines of interest |
|------|------------------|
| `src/download_service.py` | `generate_download_token` (L11), `validate_download_token` (L23), `fetch_github_release` (L32) |
| `src/routes/account_routes.py` | `login` (L143), `get_token` (L198), `download` (L266) |
| `src/account.py` | `User` model, `generate_verification_token` (L37), `is_reset_token_valid` (L54) |
| `src/config.py` | `GITHUB_PAT`, `SECRET_KEY` wiring (L51–55) |
| `templates/index.html` | `revealDownloadToken()` (L605), download section UI (L226–274) |
| `templates/login.html` | Post-login token display (L115–125), fetch `/api/account/login` (L147) |

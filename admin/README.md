# Easy OKAPI — Admin Console (secret / local-only)

A tiny local web app to **revoke** or **reinstate** a customer's Easy OKAPI
license by email. It forwards to the production server's shared-secret admin API
and attaches the `X-Admin-Key` header — the key stays in this local process and
never reaches the browser.

> ⚠️ This lives on the secret **`offline`** branch and is meant to run **only on
> the admin's machine**. Do **not** deploy it, and do **not** push this branch to
> a public remote. The `.env` (which holds the real key) is gitignored.

## How revocation works

1. You enter a customer email and click **Revoke license**.
2. The server marks every machine seat for that account `revoked` and emails the
   customer that their license was deactivated.
3. Effective immediately: the AI assistant and in-app auto-update stop working
   for that customer. The desktop app itself is blocked the next time it checks
   in online (once the client-side license check ships — see the main branch
   plan).
4. **Reinstate** clears the flag on every seat (no email).

## Setup

```bash
cd admin
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env and paste the ADMIN_API_KEY
python app.py                 # opens http://127.0.0.1:7800
```

The same `ADMIN_API_KEY` must be set on the server (Heroku config var). Generate
one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it on the server:

```bash
heroku config:set ADMIN_API_KEY=<the-key> -a easysensor-kit
```

## API it calls (server, `online` branch)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/admin/users?q=&limit=` | List/search registered accounts (name/email substring) |
| `GET`  | `/api/admin/lookup?email=` | Read a user + their machine seats |
| `POST` | `/api/admin/revoke` | `{email, revoked}` → flip all seats, email on revoke |

The console auto-loads the user list on open; click any row to load that
account's machines, then Revoke / Reinstate.

All require the `X-Admin-Key` header and return `503` if the server has no
`ADMIN_API_KEY` configured.

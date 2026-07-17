# Easy OKAPI — Admin Console (secret / local-only)

A tiny local web app to **revoke**/**reinstate** a customer's Easy OKAPI license,
**ban**/**unban** their account, or **remove** a machine seat — all by email. It
forwards to the production server's shared-secret admin API and attaches the
`X-Admin-Key` header — the key stays in this local process and never reaches the
browser.

> ⚠️ This lives on the secret **`offline`** branch and is meant to run **only on
> the admin's machine**. Do **not** deploy it, and do **not** push this branch to
> a public remote. The `.env` (which holds the real key) is gitignored.

## Revoke vs Ban

This console exposes two kill-switches of different strength:

| | **Revoke license** | **Ban account** |
|---|---|---|
| Scope | One machine **seat** (`LicenseMachine.revoked`) | The whole **account** (`User.banned`) |
| App usage on every machine | Blocked | Blocked |
| AI assistant / in-app auto-update | Blocked | Blocked |
| Website sign-in | **Still allowed** | Blocked |
| Download / re-download installer | **Still allowed** | Blocked |
| Activation of a new machine | Allowed | Blocked |
| Works with zero activated seats | No effect | Fully blocked |

Use **Revoke** for a license transfer or a single-machine issue; use **Ban** to
shut a customer out entirely.

## How it works

1. You enter a customer email and click **Revoke license** or **Ban account**.
2. The server flips the flag and emails the customer that their access was
   deactivated/suspended (once, on revoke or ban).
3. Effective immediately: the AI assistant and in-app auto-update stop working,
   and the desktop app itself is blocked the next time it checks in online (its
   `/api/license/check` poll reports `revoked`). A **ban** additionally rejects
   website sign-in, download, and activation right away.
4. **Reinstate** clears the revoked flag on every seat; **Unban** lifts the
   account ban and reinstates every seat (no email on either).

## Remove machine — freeing a stuck seat

A license only covers `MAX_MACHINES_PER_LICENSE` machines at once (default **1**),
and a seat stays taken until it is explicitly released. Both normal release paths
need the machine itself:

* the **uninstaller** calls `POST /api/license/release` (added in v1.3.0 — older
  uninstallers do not, and an in-app update cannot replace the uninstaller until
  the *next* update after v1.3.1, see Rule.md §2.25); or
* the customer signs in and clicks **Deactivate** on their account page.

Neither is possible once the machine is gone — a dead disk, a reformat, a stolen
laptop, or an uninstall by an older build. The customer is then locked out of
their own license by a machine that no longer exists, and **only an admin can free
it**. That is what **Remove** is for.

Look the customer up, then use **Remove** on the machine row (or **Remove all
machines**). It frees the seat only — it touches no user data, and the customer can
activate a replacement immediately.

> ⚠️ **Removing a revoked seat un-revokes that machine.** Deleting the row lets it
> activate again into a fresh, unrevoked seat, which silently undoes the
> kill-switch. The server refuses this with `409 seat_revoked`; the console then
> asks you to confirm again before resending with `force`. If you meant to keep the
> customer shut out, use **Ban** instead — a banned account cannot re-activate, so
> removing a banned account's seats is safe.

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
| `GET`  | `/api/admin/lookup?email=` | Read a user (incl. `banned`) + their machine seats |
| `POST` | `/api/admin/revoke` | `{email, revoked}` → flip all seats, email on revoke |
| `POST` | `/api/admin/ban` | `{email, banned}` → set account-level ban, email on ban |
| `POST` | `/api/admin/machines/remove` | `{email, hwid │ all, force}` → free seat(s); `409 seat_revoked` unless `force` |

The console auto-loads the user list on open; click any row to load that
account's machines, then Revoke / Reinstate, Ban / Unban, or Remove a seat.

All require the `X-Admin-Key` header and return `503` if the server has no
`ADMIN_API_KEY` configured.

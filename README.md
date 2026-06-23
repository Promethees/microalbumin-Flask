# `offline` branch — secret local admin tooling

This is an **orphan** branch (no shared history with `main`/`online`). It holds
admin-only tools that run **on the maintainer's machine only** and must **never
be deployed or pushed to a public remote**.

## Contents

- [`admin/`](admin/) — Easy OKAPI Admin Console: a local web app to **revoke** or
  **reinstate** a customer's license by email. It calls the production server's
  shared-secret admin API (added on the `online` branch). See
  [`admin/README.md`](admin/README.md).

## Pairing with the server

The admin tool talks to two endpoints on the deployed `online` server:

| Method | Path |
|---|---|
| `GET`  | `/api/admin/lookup?email=` |
| `POST` | `/api/admin/revoke` |

Both require the `X-Admin-Key` header to equal the server's `ADMIN_API_KEY`
config var. Those endpoints ship in the `online` branch commit
*"feat(license): admin revocation kill-switch + notification email"* — deploy
that first, then set `ADMIN_API_KEY` on the server and in `admin/.env`.

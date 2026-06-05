# Activation signing keys

These are the RSA-2048 keys for **hardware-locked permanent activation tokens**.

| File | Secrecy | Where it belongs |
|------|---------|------------------|
| `activation_private.pem` | **SECRET** | Server only, as the `ACTIVATION_PRIVATE_KEY` env var. Never commit. |
| `activation_public.pem`  | Public    | Embedded in the desktop client at `src/activation_pubkey.py`. |

Both `.pem` files are git-ignored (see `.gitignore`). They are kept here only as
local working copies; the authoritative locations are the server env var and the
embedded client constant.

## How it fits together

1. The online server signs the **permanent activation token** (RS256) with the
   private key and embeds an `hwid` claim (the machine fingerprint).
2. The desktop client verifies that token offline with the embedded public key
   and checks that the `hwid` claim matches the machine it is running on.
3. Because the client never holds the private key, a user cannot forge a token
   for their own machine; because the token is bound to one `hwid`, copying it to
   another machine fails the local check (and server-side seat binding).

## Setting the server env var

```bash
# Heroku / generic
export ACTIVATION_PRIVATE_KEY="$(cat keys/activation_private.pem)"
# or, on Heroku, paste the PEM (with real newlines) into a config var.
```

The server derives the public key from the private key at runtime, so only
`ACTIVATION_PRIVATE_KEY` needs to be configured there.

## Rotating the keys

Regenerate with:

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/activation_private.pem
openssl rsa -in keys/activation_private.pem -pubout -out keys/activation_public.pem
```

Then update `src/activation_pubkey.py` with the new public PEM and set the new
private key on the server. **Rotating invalidates every existing permanent
token** — users would have to re-activate, so rotate only on key compromise.

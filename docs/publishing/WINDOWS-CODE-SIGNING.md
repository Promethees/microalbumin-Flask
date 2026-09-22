# Windows — code-signing submission packet

Target: **Authenticode-signed direct download**, no Microsoft Store.
Outcome: `EasyOKAPI_Setup_<version>.exe` shows *Center for Bioscience and
Biotechnology…* on the UAC prompt instead of *Unknown publisher*, and stops being
blocked by SmartScreen.

Read [`README.md`](README.md) first — all the values below come from its master
fact sheet.

There is no Microsoft submission and no certification here. Microsoft is not the
counterparty: a **commercial certificate authority** is. What you submit is
organisation-identity evidence to that CA, and what you get back is a certificate
whose Subject is your organisation's legal name.

---

## 1. Choose the certificate type first

Everything else follows from this choice.

| | OV (Organization Validation) | EV (Extended Validation) |
|---|---|---|
| Identity checks | Organisation exists, address, phone, your authority | The same, stricter, plus more documentary evidence |
| Indicative cost | lower | higher |
| Key storage | Hardware token or cloud HSM (mandatory since June 2023) | Hardware token or cloud HSM |
| SmartScreen | Reputation must be **earned** over installs and time | Immediate reputation on first signed release |
| Issue time | days to ~2 weeks | often longer |

**Recommendation: OV**, unless a warning-free experience from the very first
download is a hard requirement. Easy OKAPI is downloaded by a known research
audience from the project's own site, and the reputation gap closes as installs
accumulate. If early users cannot be walked past a SmartScreen prompt, buy EV and
skip that phase entirely.

Two things people expect and do not get:

- **A `.pfx` in a GitHub secret no longer works.** Since June 2023 the CA/Browser
  Forum baseline requirements put publicly trusted code-signing private keys on
  FIPS 140-2 Level 2 (or Common Criteria EAL4+) hardware. No CA will issue an
  exportable file. See §3 for what CI looks like instead.
- **Signing does not silence SmartScreen on day one** with an OV certificate. It
  starts a reputation record. Re-using the same certificate across releases is
  what builds it; changing certificates resets it.

---

## 2. Documents to submit to the CA

CAs differ in wording but verify the same four things. Prepare all of it before
applying — a half-answered application stalls for weeks.

### 2.1 Organisation is real and legally registered

- Establishment decision / business registration for the entity in the fact
  sheet, in Vietnamese, with a certified English translation.
- Tax code (mã số thuế).
- If CBBiotec is a unit of the University of Science rather than a separate legal
  person, the applicant must be **the university**, with CBBiotec at most a
  department line. See README §Open items — resolve this before applying, because
  the certificate Subject cannot be changed afterwards without re-issuing.

### 2.2 Address is real

- The registered address as it appears in the registration document.
- Independent corroboration: a government registry entry, a Dun & Bradstreet
  record, or a recent utility/bank document naming the entity at that address.

### 2.3 Phone is real and answers

- A landline listed in a source the CA can check independently (a public
  directory, the university's official site, or a D-U-N-S record) — **not** a
  number supplied only on the application form.
- Someone must answer and be able to confirm the applicant works there. Tell the
  switchboard the call is coming; a failed callback is the most common cause of
  a stalled application.

### 2.4 You are authorised to request it

- Employment or appointment evidence.
- Government-issued photo ID.
- Where the applicant is not the legal representative, a signed authorisation
  letter on letterhead.

### 2.5 Application field values

| Field | Value |
|---|---|
| Organisation name | ‹exact registered legal name — becomes the certificate Subject CN› |
| Department | Center for Bioscience and Biotechnology (CBBiotec) |
| Address | 227 Nguyen Van Cu, Ward 4, Cho Quan ward, Ho Chi Minh City, Vietnam |
| Country | VN |
| Phone | ‹verifiable landline› |
| Applicant email | ‹address on the entity's domain — see README §Open items› |
| Website | https://www.easysensorkit.cbbiotec.vn |
| Certificate type | Code Signing, OV |
| Intended use | Signing a desktop scientific application distributed from the organisation's own website |

**The Subject CN must match `VIAddVersionKey "CompanyName"` in
`installer-win/setup.nsi` and `setup-frozen.nsi`.** They currently read
`Center for Bioscience and Biotechnology (CBBiotec), HCMUS-VNU`. Once the CA
confirms the exact registered name, make both say the same thing.

---

## 3. Signing in CI, with the key on hardware

Two workable shapes. Pick one before applying — it decides which product you buy.

**A. Cloud signing service (recommended for CI).** Azure Trusted Signing, or a
CA's own cloud-HSM signing (DigiCert KeyLocker, SSL.com eSigner, Sectigo cloud
signing). The key never leaves the provider's HSM; CI authenticates and submits a
digest. This is the only shape that works on a hosted GitHub runner.

> Verify eligibility before committing. Azure Trusted Signing restricts which
> countries and what organisation age it will validate, and the rules change.
> Confirm that a Vietnamese public-sector entity qualifies *before* buying — if
> not, a CA cloud-HSM product is the fallback.

**B. Physical USB token.** Cheaper, but the token must be plugged into the
machine that signs, so releases can only be signed from a self-hosted runner or
by hand. Workable if releases are infrequent; it makes automated release
impossible otherwise.

### What to sign, and in what order

Sign inside-out. Signing the installer does not sign what it installs.

1. `dist/EasyOKAPI/EasyOKAPI.exe` — the frozen application
2. Any `.exe` / `.dll` PyInstaller placed in `dist/EasyOKAPI/_internal/` that is
   ours rather than a third party's already-signed binary
3. `EasyOKAPI_Setup_<version>.exe` — the NSIS installer, **after** `makensis`
4. `make-uninstaller.exe` and the emitted `Uninstall.exe`, if you want the
   uninstall path to show a publisher too

Always timestamp — without `/tr`, every signature expires when the certificate
does, and previously shipped installers start warning:

```powershell
signtool sign /fd SHA256 /td SHA256 `
  /tr http://timestamp.digicert.com `
  /n "‹exact certificate subject›" `
  "EasyOKAPI_Setup_1.5.8.exe"

signtool verify /pa /v "EasyOKAPI_Setup_1.5.8.exe"
```

### Fix before the first signed release

| Fix | Why |
|---|---|
| Add a version resource to `EasyOKAPI.exe` | `easyokapi.spec` passes no `version=` to `EXE()`, so the installed application has no CompanyName, no ProductVersion and no copyright — the installer shows a publisher and the app it installs does not. Generate a version-info file from `APP_VERSION` in `tools/package.py` and pass it to the spec. |
| Keep `VIAddVersionKey "CompanyName"` and the certificate Subject identical | Windows shows one and validates the other; a mismatch reads as a repackaged binary. |
| Keep the Add/Remove Programs `Publisher` value identical too | `installer-win/setup-frozen.nsi`, `WriteRegStr … "Publisher"`. |
| Sign every release with the **same** certificate | SmartScreen reputation is per-certificate. Renewing is fine; switching CAs restarts the clock. |

---

## 4. Per-release checklist

- [ ] `makensis /DAPP_VERSION=<version> setup-frozen.nsi` succeeds and the
      licence page renders — the EULA page is compiled in from
      `legal/EULA.rtf`, so a missing or stale file is a build failure, not a
      runtime one
- [ ] `python3 legal/render_license.py --check` passes (CI runs this)
- [ ] Frozen `EasyOKAPI.exe` signed, then the installer signed, both timestamped
- [ ] `signtool verify /pa /v` clean on both
- [ ] File Properties → Details shows Easy OKAPI, the version, and the
      organisation as CompanyName
- [ ] Digital Signatures tab shows the certificate and a countersignature
- [ ] Installed, then checked in Settings → Apps: the Publisher column shows the
      organisation
- [ ] Downloaded through a browser and run on a **clean** Windows VM — not the
      build machine. SmartScreen judges files by download reputation, and a
      locally built file has no Mark-of-the-Web, so it will not reproduce what a
      user sees.
- [ ] Licence page appears before the activation-token page, and Next stays
      disabled until the acceptance checkbox is ticked
- [ ] `$INSTDIR\legal\` contains `EULA.txt`, `PRIVACY.md` and `LICENSE`
- [ ] `/legal/eula` and `/legal/privacy` open in the running app with the network
      disconnected

---

## 5. If the Microsoft Store is ever reconsidered

Everything above is the direct-download path. The Store would additionally
require, and currently block on:

| Requirement | Conflict in Easy OKAPI today |
|---|---|
| MSIX packaging | The product is an NSIS installer that writes to `Program Files`, edits the `hosts` file and creates its own data folder |
| No self-updating outside the Store | `src/update_service.py` swaps the app's own binary |
| No editing the `hosts` file | `setup-frozen.nsi` maps `easyokapi.com` to `127.0.0.1` |
| Store-managed licensing | The product has its own activation, hardware binding and remote kill-switch |
| Age rating, Store listing assets, certification | Not prepared |

Publisher identity verification in Partner Center is comparable work to the CA
verification above and can reuse the same documents — but the packaging changes
are real engineering. Reopen only if Store placement becomes a requirement in
itself.

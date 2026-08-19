# Publishing Easy OKAPI — submission packet

Everything needed to publish signed Easy OKAPI builds under a verified publisher
identity, for the two channels chosen for v1.4.x:

| Channel | Document | What it gets you |
|---|---|---|
| macOS, outside the App Store | [`APPLE-DEVELOPER-ID.md`](APPLE-DEVELOPER-ID.md) | Apple Developer Program enrolment, a Developer ID Application certificate, and notarised DMGs that open with no Gatekeeper warning |
| Windows, direct download | [`WINDOWS-CODE-SIGNING.md`](WINDOWS-CODE-SIGNING.md) | An Authenticode certificate bound to a verified organisation, a signed `EasyOKAPI_Setup.exe`, and a SmartScreen reputation that stops the "unrecognised app" block |

Neither channel is a store. There is **no App Review and no Microsoft Store
certification** on this path — the gate is *identity verification* (proving the
publisher is a real, verifiable organisation) plus, on macOS, an automated
malware scan. That is why the bulk of both documents is paperwork rather than
app metadata.

> The Mac App Store and the Microsoft Store were considered and are **out of
> scope**. Easy OKAPI opens arbitrary user-chosen directories, talks to a USB
> serial device, runs a local HTTP server, and updates itself by swapping its own
> binary. Every one of those conflicts with App Sandbox / MSIX packaging
> requirements. Adding a store target means rearchitecting those four things, not
> refiling paperwork.

The mechanics of signing and notarising on macOS are already written up in
[`../../installer-mac/SIGNING.md`](../../installer-mac/SIGNING.md). This packet
does not repeat them; it covers what to submit *to become* the publisher those
commands sign as, and it flags where SIGNING.md's placeholder identity is now
out of step (see §Open items).

---

## 1. Master fact sheet

Every form in both documents pulls from this table. Fill the `‹…›` values once,
here, and copy from here — a mismatch between what you tell Apple, what you tell
the certificate authority, and what is compiled into the binary is the single
most common cause of a rejected identity check.

### Publisher

| Field | Value |
|---|---|
| Legal entity (English) | Center for Bioscience and Biotechnology (CBBiotec), University of Science, Vietnam National University Ho Chi Minh City |
| Legal entity (Vietnamese, as registered) | ‹exact registered name — must match the establishment decision / business registration verbatim› |
| Short/display publisher name | CBBiotec — HCMUS, VNU-HCM |
| Entity type | ‹public university unit / centre — confirm whether CBBiotec has its own legal personality, see §Open items› |
| Registration or decision number | ‹…› |
| Tax code (mã số thuế) | ‹…› |
| Registered address | 227 Nguyen Van Cu, Ward 4, Cho Quan ward, Ho Chi Minh City, Vietnam |
| Public phone (must be independently verifiable) | ‹…› |
| Website | https://www.easysensorkit.cbbiotec.vn |
| Authorised signatory (name, title) | ‹…› |
| Signatory work email (on the entity's domain, not Gmail) | ‹…› |
| D-U-N-S number | ‹…› — required by Apple, see APPLE-DEVELOPER-ID.md §2 |

### Product

| Field | Value |
|---|---|
| Product name | Easy OKAPI |
| Full name | Easy OKAPI — Open-colorimeter Kinetics Analysis Platform |
| Current version | 1.5.2 (`CLAUDE.md`, `installer-*/`, injected as `APP_VERSION`) |
| Category | Developer tools / Science & research (not Medical) |
| macOS bundle identifier | `vn.cbbiotec.easyokapi` — see §Open items, not yet set in the build |
| Windows product name in the version resource | Easy OKAPI (`installer-win/setup*.nsi`, `VIAddVersionKey`) |
| Windows installer file | `EasyOKAPI_Setup_<version>.exe` |
| macOS installer file | `EasyOKAPI_v<version>.dmg` |
| Linux installer file | `EasyOKAPI_linux_v<version>.tar.gz` |
| Source licence | MIT (`LICENSE`) |
| Distribution licence | `legal/EULA.md` |
| Privacy notice | `legal/PRIVACY.md` and https://www.easysensorkit.cbbiotec.vn/privacy |
| Terms of Service | https://www.easysensorkit.cbbiotec.vn/terms |
| Support URL | https://www.easysensorkit.cbbiotec.vn |
| Support email | tqmthong@gmail.com — see §Open items |
| Copyright | © 2025–2026 Trà Quang Minh Thông and CBBiotec, HCMUS–VNU |

### Standard answers

These recur across enrolment forms, certificate applications and notarisation
metadata. Answer them the same way every time.

| Question | Answer |
|---|---|
| Is this a medical device or health app? | **No.** Research and education tool only; `legal/EULA.md` §1 says so in the product itself. |
| Does it collect personal data? | Yes, minimally: account email + name (on the website), and a per-machine hardware fingerprint for licensing. Detailed in `legal/PRIVACY.md`. |
| Does it collect health data? | **No.** Users are told in the EULA and privacy notice not to enter patient identifiers. |
| Does it show ads or track users for advertising? | No. |
| Is it directed at children? | No. Minimum age 16. |
| Does it use encryption? | Yes, but only standard, publicly available libraries: HTTPS/TLS for transport and RS256 signature verification for licence tokens. No proprietary cryptography, no encryption offered to the user. Qualifies for the usual mass-market/publicly-available exemptions — see `legal/EULA.md` §12.3. |
| Does it contain third-party open-source code? | Yes; each component under its own licence. |
| Does it self-update? | Yes, from the publisher's own server, gated on a valid licence seat. |
| Does it require network access? | For activation, licence checks, updates and the AI assistant. Analysis itself works offline. |

---

## 2. Order of work

Identity verification is the long pole — weeks, not days — and everything else
blocks on it. Start both in parallel.

1. **Settle the legal entity** (§Open items). Everything downstream inherits it.
2. **Get a D-U-N-S number** for that entity — free, but allow up to ~5 business
   days, longer for a Vietnamese public-sector body. Apple will not enrol an
   organisation without one.
3. **In parallel:** start the Apple Developer Program organisation enrolment
   (`APPLE-DEVELOPER-ID.md`) and the Authenticode certificate application
   (`WINDOWS-CODE-SIGNING.md`). Both re-verify the same facts independently.
4. **Once certificates are in hand:** wire signing into CI, ship one signed
   release per platform, and verify on a clean machine — a machine that has
   never run an unsigned Easy OKAPI, or Gatekeeper and SmartScreen will give you
   a falsely clean result.
5. **Windows only:** budget for SmartScreen reputation to accrue over the first
   few hundred installs unless you buy an EV certificate.

---

## 3. Open items

Resolve these before submitting anything. Each one will fail a verification
check or produce a binary that contradicts its own paperwork.

1. **Which entity actually signs?** The chosen publisher is CBBiotec / HCMUS–VNU,
   but `installer-mac/SIGNING.md` is written throughout against
   `Developer ID Application: HTBiotec Co. Ltd`, and until this change
   `installer-win/setup-frozen.nsi` registered `Publisher = "HTBiotec"` in
   Add/Remove Programs. Both certificate authorities verify the entity name
   against public records, so a centre inside a public university and a private
   company are not interchangeable. Decide, then make the certificate subject,
   the NSIS `CompanyName` / `Publisher`, and SIGNING.md all say the same thing.
   *If CBBiotec has no separate legal personality*, the enrolling entity has to
   be the University of Science, VNU-HCM, with CBBiotec as the display name.
2. **A support email on the entity's domain.** `tqmthong@gmail.com` is a personal
   Gmail address. Apple and every commercial CA will use the domain of the
   contact address as one signal that the applicant speaks for the organisation,
   and a free-mail address weakens or blocks that. Set up something like
   `easyokapi@cbbiotec.vn` before applying, and update `legal/EULA.md`,
   `legal/PRIVACY.md`, `templates/terms.html` and `templates/privacy.html` when
   you do.
3. **macOS bundle identifier.** The `.app` is produced by `osacompile`, which
   assigns `com.apple.ScriptEditor.id.EasyOKAPI`. That is Apple's identifier
   namespace, not ours. Set `CFBundleIdentifier` to `vn.cbbiotec.easyokapi` in
   `installer-mac/build-dmg*.sh` before the first notarisation submission, so
   the notarisation record and every later update refer to the same app.
4. **Hardware-protected signing key (Windows).** Since June 2023 publicly
   trusted code-signing keys must live on FIPS 140-2 Level 2 (or equivalent)
   hardware. A `.p12` file in a GitHub secret is no longer an option for
   Authenticode. See `WINDOWS-CODE-SIGNING.md` §3 for the two workable CI shapes.
5. **PyInstaller version resource.** `installer-win/setup*.nsi` now carry a
   version resource, but `EasyOKAPI.exe` itself does not — `easyokapi.spec`
   passes no `version=` to `EXE()`. The installer will show a publisher and the
   app it installs will not. Add a version-info file to the spec before signing.
6. **Confirm the registered address.** 227 Nguyen Van Cu is the University of
   Science's address; verify the ward and the exact form CBBiotec's registration
   uses, and reconcile it with the address printed in
   `legal/EULA.md`, `legal/PRIVACY.md` and the two website legal pages.

---

## 4. Keeping the legal text in step

The licence shown by the Windows installer and shipped in the DMG and tarball is
generated, not hand-written:

```bash
python3 legal/render_license.py           # regenerate legal/EULA.txt + legal/EULA.rtf
python3 legal/render_license.py --check   # CI runs this; fails if either is stale
```

Edit `legal/EULA.md`, never the `.txt` or `.rtf`. When the licence or the privacy
notice changes materially, bump the version and effective date in **all four**
places that carry them: `legal/EULA.md`, `legal/PRIVACY.md`, and `LEGAL_VERSION`
/ `LEGAL_EFFECTIVE` in the web app's `main.py` (the `online` branch).

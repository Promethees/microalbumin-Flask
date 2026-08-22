# Apple — Developer ID submission packet

Target: **notarised Developer ID distribution**, outside the Mac App Store.
Outcome: `EasyOKAPI_v<version>.dmg` opens on any Mac with no Gatekeeper warning.

Read [`README.md`](README.md) first — all the values below come from its master
fact sheet. The `codesign` / `notarytool` / `stapler` mechanics are in
[`../../installer-mac/SIGNING.md`](../../installer-mac/SIGNING.md); this document
covers what to submit to Apple to become the publisher those commands sign as.

There is **no App Review** on this path. What Apple checks is (a) that the
enrolling organisation is real and that you are authorised to bind it, and
(b) that each uploaded build passes an automated malware scan. Plan for the first
to take weeks and the second to take minutes.

---

## 1. What you are applying for

| | |
|---|---|
| Programme | Apple Developer Program — **Organization** enrolment (not Individual) |
| Cost | USD 99 / year |
| Certificate | **Developer ID Application** (and Developer ID Installer only if you later ship a `.pkg`; the current DMG does not need it) |
| Not needed | Mac App Store distribution certificate, App Store Connect app record, App Review submission, age rating, screenshots, or a privacy "nutrition label" — those are Mac App Store artefacts |

**Individual vs Organization.** Individual enrolment is faster and needs no
D-U-N-S, but the certificate's Subject is a *person's name*, and that is what
macOS shows and what appears in the signature. Since the decision is to publish
as CBBiotec / HCMUS–VNU, enrol as an organisation. Do not enrol as an individual
"for now" — moving a Developer ID between accounts later means re-signing and
re-notarising every artefact, and users who trusted the old identity see a new one.

---

## 2. Documents and facts to have ready

Apple verifies the organisation itself, then verifies that you personally are
entitled to sign for it.

### 2.1 Organisation identity

| Item | Notes |
|---|---|
| **D-U-N-S number** | Mandatory. Free from Dun & Bradstreet via Apple's lookup at <https://developer.apple.com/enroll/duns-lookup/>. Search first — the university may already have one. If not, request it and allow up to ~5 business days; Vietnamese public-sector entities often take longer and may need supporting documents. |
| **Legal entity name** | Must match the D-U-N-S record *exactly*, character for character. This becomes the Subject of the certificate and is what `spctl` reports. |
| **Legal entity address & phone** | Must match the D-U-N-S record. The phone must be independently verifiable — Apple may call it. |
| **Website** | Must be live and clearly belong to the entity. `https://www.easysensorkit.cbbiotec.vn` works; make sure the legal pages (`/terms`, `/privacy`) and an obvious mention of CBBiotec are reachable from the front page. |
| **Establishment decision / business registration** | Vietnamese entity documents. Apple usually works from D-U-N-S alone, but has these scanned and ready in case verification escalates. |

### 2.2 Your authority to enrol

| Item | Notes |
|---|---|
| **Legal authority to bind the entity**, or a signed letter of authorisation from someone who has it | Apple asks explicitly and may request written evidence. For a university centre this is normally the Director or an authorised deputy. |
| **Work email on the entity's domain** | See README §Open items — a Gmail address weakens this materially. |
| **Apple ID with two-factor authentication enabled** | Use an account owned by the organisation, not a personal one. If a personal Apple ID enrols, the membership follows that person out of the institution. |

### 2.3 Application answers

| Field | Value |
|---|---|
| Entity type | ‹public university unit / research centre — from README fact sheet› |
| Legal entity name | ‹exact D-U-N-S name› |
| D-U-N-S | ‹…› |
| Website | https://www.easysensorkit.cbbiotec.vn |
| Your role | ‹title› |
| What you plan to distribute | Scientific data-analysis software distributed directly from the organisation's website, not through the Mac App Store |

**Timeline.** D-U-N-S: up to a week. Enrolment review: typically 2 days to 2
weeks, longer for institutional applicants. Certificate issue after approval:
minutes.

---

## 3. After approval — one-time setup

1. Create the **Developer ID Application** certificate
   (`installer-mac/SIGNING.md` §2).
2. Record the **Team ID** (10 characters) and the full signing identity string.
3. Create an **app-specific password** for `notarytool`
   (`installer-mac/SIGNING.md` §4).
4. Store the CI secrets (`installer-mac/SIGNING.md` §3). Unlike Windows, Apple
   does **not** require the code-signing key to live on an HSM, so a
   base64-encoded `.p12` in GitHub Actions secrets remains acceptable here.
5. **Update `installer-mac/SIGNING.md`** — it is written throughout against
   `Developer ID Application: HTBiotec Co. Ltd (ABCD1234EF)`. Replace the
   placeholder identity with the real one so nobody signs with the wrong subject
   by copy-paste.

### Fix before the first submission

| Fix | Why |
|---|---|
| Set `CFBundleIdentifier` to `vn.cbbiotec.easyokapi` in `installer-mac/build-dmg.sh` and `build-dmg-frozen.sh` | The `.app` comes from `osacompile`, which stamps `com.apple.ScriptEditor.id.EasyOKAPI` — Apple's own identifier namespace. Notarisation records are keyed on the bundle ID; changing it later fragments the app's history. |
| Set `CFBundleShortVersionString` / `CFBundleVersion` from `APP_VERSION` | Otherwise every build looks like version 1.0 to Apple. |
| Confirm `installer-mac/entitlements.plist` is still minimal | It currently grants Apple Events automation and unsigned executable memory, both genuinely required by the AppleScript applet under the hardened runtime. Do not add entitlements speculatively — each one is a question you may be asked. |

---

## 4. Per-release checklist

Signing must happen inside-out: the frozen binary, then the `.app`, then the DMG.
Signing the DMG does not sign what is inside it.

```bash
export APP_VERSION=1.5.3
export SIGNING_IDENTITY="Developer ID Application: ‹entity› (‹TEAMID›)"
```

- [ ] `python tools/package.py --encode` — build `dist/EasyOKAPI/`
- [ ] Sign the frozen bundle's executables and dylibs with `--options runtime`
      (hardened runtime is a hard requirement for notarisation)
- [ ] `bash installer-mac/build-dmg-frozen.sh` — builds and signs the `.app`
      (it already honours `SIGNING_IDENTITY`) and packages the DMG
- [ ] Verify the app: `codesign --verify --deep --strict --verbose=2` and
      `spctl --assess --type exec -vvv` → expect `source=Developer ID`
- [ ] `codesign --sign "$SIGNING_IDENTITY" EasyOKAPI_v$APP_VERSION.dmg`
- [ ] `xcrun notarytool submit … --wait` → expect `status: Accepted`
- [ ] On rejection: `xcrun notarytool log <submission-id>` — it names the exact
      offending binary. Usually an unsigned nested dylib in the PyInstaller
      bundle, or a missing hardened runtime flag.
- [ ] `xcrun stapler staple EasyOKAPI_v$APP_VERSION.dmg` — without this the DMG
      needs a live network to validate on the user's machine
- [ ] `xcrun stapler validate` and
      `spctl --assess --type open --context context:primary-signature -v` →
      expect `source=Notarized Developer ID`
- [ ] Confirm `Legal/` on the mounted DMG contains the licence, the privacy
      notice and the MIT licence (added by `build-dmg*.sh`)
- [ ] Install on a Mac that has **never** run Easy OKAPI. Gatekeeper caches
      per-app decisions, so a machine that once bypassed the warning will not
      reproduce a user's first-run experience.

Notarisation covers the artefact you submitted. Rebuilding the DMG for any
reason — even a one-character change — means signing, notarising and stapling
again.

---

## 5. If the Mac App Store is ever reconsidered

Everything above is the Developer ID path. The App Store would additionally
require, and currently block on:

| Requirement | Conflict in Easy OKAPI today |
|---|---|
| App Sandbox | Reads and writes user-chosen directories anywhere on disk |
| No arbitrary USB device access | Talks to the PyBadge over a USB CDC serial port |
| No self-modifying installs | `src/update_service.py` swaps the app's own binary |
| No bundled interpreter running downloaded code | The source build clones a repo and creates a venv |
| App Review of the licensing model | The activation gate, hardware binding and remote kill-switch would each be reviewed against Apple's rules on external purchases and device identifiers |

That is an architecture change, not a paperwork change. Reopen only if App Store
placement becomes a requirement in itself.

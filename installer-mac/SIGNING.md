# Apple Code-Signing & Notarization Guide

Without signing and notarization, macOS Gatekeeper blocks the DMG with
_"EasyOKAPI cannot be opened because it is from an unidentified developer"_.
After completing this guide every user gets a clean install: no warnings,
no right-click workarounds.

---

## How it works

```
Developer ID cert  ─── codesign ──▶  EasyOKAPI.app  ──▶  EasyOKAPI.dmg
                                                              │
                                                Apple notarytool (upload)
                                                              │
                                                     Apple scans for malware
                                                              │
                                                   xcrun stapler (attach ticket)
                                                              │
                                                  ✅ Gatekeeper-approved DMG
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Apple Developer Program membership | $99 / year — [developer.apple.com/programs](https://developer.apple.com/programs/) |
| Xcode Command Line Tools | `xcode-select --install` |
| **Developer ID Application** certificate | Created on developer.apple.com (not a Mac App Store cert) |

---

## Step 1 — Join the Apple Developer Program

1. Go to [developer.apple.com/programs/enroll](https://developer.apple.com/programs/enroll/)
2. Sign in with your Apple ID (use the company/organisation Apple ID for HTBiotec)
3. Complete enrolment and pay the annual fee
4. Allow 24–48 hours for approval

---

## Step 2 — Create a Developer ID Application Certificate

1. Open **Xcode → Settings → Accounts** and add your Apple ID
2. Click **Manage Certificates… → + → Developer ID Application**
3. Xcode creates and installs the certificate into your login Keychain automatically

Alternatively, via the web:

1. [developer.apple.com/account/resources/certificates/add](https://developer.apple.com/account/resources/certificates/add)
2. Choose **Developer ID Application** → Continue
3. Generate a Certificate Signing Request (CSR) from **Keychain Access → Certificate Assistant → Request a Certificate from a Certificate Authority**
4. Upload the CSR → download and double-click the resulting `.cer` file

Verify the certificate is installed:

```bash
security find-identity -v -p codesigning
```

Expected output (your Team ID will differ):

```
1) AABBCCDD1122... "Developer ID Application: HTBiotec Co. Ltd (ABCD1234EF)"
```

Note the quoted string — this is your **signing identity**.

---

## Step 3 — Export the Certificate for CI/CD

GitHub Actions runners don't have access to your Keychain, so you export
the certificate as a password-protected `.p12` file and store it as a secret.

1. Open **Keychain Access**
2. Find **Developer ID Application: HTBiotec…** under **My Certificates**
3. Right-click → **Export** → choose **Personal Information Exchange (.p12)**
4. Set a strong export password and save as `certificate.p12`
5. Base64-encode it:

```bash
base64 -i certificate.p12 | pbcopy   # copies to clipboard
```

6. Add the following **Actions Secrets** in your repo
   (Settings → Secrets and variables → Actions → New repository secret):

| Secret name | Value |
|---|---|
| `MACOS_CERTIFICATE` | The base64 string from above |
| `MACOS_CERTIFICATE_PASSWORD` | The export password you chose |
| `MACOS_KEYCHAIN_PASSWORD` | Any strong random string (used only for the temp CI keychain) |
| `MACOS_SIGNING_IDENTITY` | e.g. `Developer ID Application: HTBiotec Co. Ltd (ABCD1234EF)` |
| `APPLE_ID` | The Apple ID email used for the Developer account |
| `APPLE_APP_PASSWORD` | App-specific password — see Step 4 |
| `APPLE_TEAM_ID` | Your 10-character Team ID, e.g. `ABCD1234EF` |

---

## Step 4 — Create an App-Specific Password

Notarization requires a password specific to the `notarytool` app, **not** your
main Apple ID password.

1. Go to [appleid.apple.com](https://appleid.apple.com/) → Sign In
2. **App-Specific Passwords → + Generate an app-specific password**
3. Label it `notarytool-easyokapi`
4. Copy the generated password (shown only once) → add it as `APPLE_APP_PASSWORD`

---

## Step 5 — Find Your Team ID

```bash
# If you have Xcode installed:
xcrun altool --list-providers -u "your@apple-id.com" -p "app-specific-password"

# Or read it from your installed certificate:
security find-identity -v -p codesigning | grep "Developer ID"
# The 10-char code in parentheses at the end is your Team ID
```

---

## Step 6 — Sign the App Bundle (manual / local)

After `build-dmg.sh` creates `EasyOKAPI.app` inside `tmp_dmg_root/` (before
it is packaged into the DMG), sign it:

```bash
SIGNING_IDENTITY="Developer ID Application: HTBiotec Co. Ltd (ABCD1234EF)"

codesign \
    --deep \
    --force \
    --verify \
    --verbose \
    --sign "$SIGNING_IDENTITY" \
    --options runtime \
    --entitlements installer-mac/entitlements.plist \
    tmp_dmg_root/EasyOKAPI.app
```

Verify:

```bash
codesign --verify --deep --strict --verbose=2 tmp_dmg_root/EasyOKAPI.app
spctl --assess --type exec -vvv tmp_dmg_root/EasyOKAPI.app
# Expected: "accepted  source=Developer ID"
```

---

## Step 7 — Sign & Notarize the DMG

After `build-dmg.sh` produces `EasyOKAPI_v1.1.4.dmg`:

```bash
DMG="EasyOKAPI_v1.1.4.dmg"

# Sign the DMG itself
codesign --sign "$SIGNING_IDENTITY" "$DMG"

# Upload to Apple for notarization (waits for the result)
xcrun notarytool submit "$DMG" \
    --apple-id   "your@apple-id.com" \
    --password   "app-specific-password" \
    --team-id    "ABCD1234EF" \
    --wait

# Attach the notarization ticket so the DMG works offline
xcrun stapler staple "$DMG"
```

---

## Step 8 — Verify the Final DMG

```bash
# Stapler ticket is present
xcrun stapler validate "$DMG"

# Gatekeeper accepts it
spctl --assess --type open --context context:primary-signature -v "$DMG"
# Expected: "accepted  source=Notarized Developer ID"
```

---

## Automating in GitHub Actions

Add four new steps to the `build-macos` job in `.github/workflows/main.yml`.

### Where to insert them

```
existing: Inject version and auth URL
existing: Build DMG                ← app is built here; sign app BEFORE DMG packaging
NEW:      Sign app (before DMG)    ← must run BEFORE build-dmg.sh packages the .app
NEW:      Sign DMG
NEW:      Notarize DMG
NEW:      Staple DMG
existing: Upload DMG artifact
```

Because `build-dmg.sh` both builds the `.app` and immediately packages it into
the DMG, the simplest approach is to split the build into two phases by setting
an environment variable that pauses packaging, or by adding signing inline.
The cleanest change is to add a `SIGNING_IDENTITY` env-check inside
`build-dmg.sh` and sign the `.app` right after `osacompile`:

```bash
# Inside build-dmg.sh, after the osacompile + icon copy block:
if [ -n "${SIGNING_IDENTITY:-}" ]; then
    echo "🔏 Signing EasyOKAPI.app…"
    codesign --deep --force --verify \
        --sign "$SIGNING_IDENTITY" \
        --options runtime \
        --entitlements "$SOURCE_DIR/entitlements.plist" \
        "$TMP_DIR/EasyOKAPI.app"
    echo "✅ App signed."
fi
```

Then in the workflow, after "Build DMG", add:

```yaml
      - name: Import code-signing certificate
        if: ${{ env.MACOS_CERTIFICATE != '' }}
        env:
          MACOS_CERTIFICATE:          ${{ secrets.MACOS_CERTIFICATE }}
          MACOS_CERTIFICATE_PASSWORD: ${{ secrets.MACOS_CERTIFICATE_PASSWORD }}
          MACOS_KEYCHAIN_PASSWORD:    ${{ secrets.MACOS_KEYCHAIN_PASSWORD }}
        run: |
          security create-keychain -p "$MACOS_KEYCHAIN_PASSWORD" build.keychain
          security default-keychain -s build.keychain
          security unlock-keychain  -p "$MACOS_KEYCHAIN_PASSWORD" build.keychain
          security set-keychain-settings -t 3600 -u build.keychain
          echo "$MACOS_CERTIFICATE" | base64 --decode > certificate.p12
          security import certificate.p12 -k build.keychain \
              -P "$MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
          security set-key-partition-list \
              -S apple-tool:,apple: -s -k "$MACOS_KEYCHAIN_PASSWORD" build.keychain
          rm certificate.p12

      - name: Build DMG
        env:
          APP_VERSION:      ${{ env.APP_VERSION }}
          SIGNING_IDENTITY: ${{ secrets.MACOS_SIGNING_IDENTITY }}
        run: |
          chmod +x ./installer-mac/build-dmg.sh
          ./installer-mac/build-dmg.sh

      - name: Sign DMG
        if: ${{ secrets.MACOS_SIGNING_IDENTITY != '' }}
        env:
          SIGNING_IDENTITY: ${{ secrets.MACOS_SIGNING_IDENTITY }}
        run: |
          codesign --sign "$SIGNING_IDENTITY" EasyOKAPI_v${{ env.APP_VERSION }}.dmg

      - name: Notarize DMG
        if: ${{ secrets.APPLE_ID != '' }}
        env:
          APPLE_ID:           ${{ secrets.APPLE_ID }}
          APPLE_APP_PASSWORD: ${{ secrets.APPLE_APP_PASSWORD }}
          APPLE_TEAM_ID:      ${{ secrets.APPLE_TEAM_ID }}
        run: |
          xcrun notarytool submit \
              EasyOKAPI_v${{ env.APP_VERSION }}.dmg \
              --apple-id  "$APPLE_ID" \
              --password  "$APPLE_APP_PASSWORD" \
              --team-id   "$APPLE_TEAM_ID" \
              --wait

      - name: Staple notarization ticket
        if: ${{ secrets.APPLE_ID != '' }}
        run: |
          xcrun stapler staple EasyOKAPI_v${{ env.APP_VERSION }}.dmg
```

All signing/notarization steps are gated on secret presence, so the workflow
continues to build unsigned DMGs on forks or branches where secrets are not set.

---

## Troubleshooting

### "The application cannot be opened" after notarization

Run `spctl` to see what Gatekeeper thinks:

```bash
spctl --assess --type open --context context:primary-signature -v EasyOKAPI.dmg
```

If it says `rejected`, check the notarization log:

```bash
xcrun notarytool log <submission-id> \
    --apple-id "your@email" --password "app-pw" --team-id "TEAMID"
```

### "resource fork, Finder information, or similar detritus" error

Run `xattr -cr EasyOKAPI.app` before signing to strip quarantine and extended
attributes left by Finder.

### "ambiguous (matches more than one certificate)"

Your Keychain has multiple Developer ID certs. Specify the full fingerprint:

```bash
security find-identity -v -p codesigning   # copy the long hex fingerprint
codesign --sign "<fingerprint>" ...
```

### Notarization rejected: "code object is not signed at all"

The `--deep` flag doesn't always reach nested executables in AppleScript apps.
Sign the inner binary explicitly first:

```bash
codesign --force --sign "$SIGNING_IDENTITY" --options runtime \
    --entitlements installer-mac/entitlements.plist \
    tmp_dmg_root/EasyOKAPI.app/Contents/MacOS/applet
codesign --force --sign "$SIGNING_IDENTITY" --options runtime \
    --entitlements installer-mac/entitlements.plist \
    tmp_dmg_root/EasyOKAPI.app
```

### Notarization takes too long

The `--wait` flag polls Apple every 30 s. Typical turnaround is 1–5 minutes.
If the job times out, poll manually:

```bash
xcrun notarytool history --apple-id "…" --password "…" --team-id "…"
xcrun notarytool log <id>  --apple-id "…" --password "…" --team-id "…"
```

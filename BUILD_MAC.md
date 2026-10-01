# Building the macOS Installer DMG

Two DMG builders live in `installer-mac/`. Both are normally run by CI
(`.github/workflows/main.yml`), not by hand — both **require `APP_VERSION`** in the
environment and exit if it is unset.

| Script | Produces | Ships |
|---|---|---|
| `build-dmg-frozen.sh` | `EasyOKAPI_v<ver>.dmg` wrapping the PyInstaller onedir | The no-source build (`ENCODE_SOURCE=true`) — see `ENCODE_BUILD_PLAN.md` |
| `build-dmg.sh` | `EasyOKAPI_v<ver>.dmg` wrapping the source tree + `setup.sh` | The source build: pyenv + venv + token-gated source download |

## Frozen DMG (the shipping path)

```bash
cd /path/to/microalbumin-Flask
python tools/package.py --encode          # produces dist/EasyOKAPI/
APP_VERSION=1.5.12 ./installer-mac/build-dmg-frozen.sh
```

The `.app` embeds the frozen binary at `Contents/Resources/EasyOKAPI/` and launches
it via `run-frozen.scpt` → `launch-frozen.sh`. No token prompt, no pyenv, no venv —
the binary creates its own per-user data directories on first run. `migrate-frozen.sh`
carries an existing source install's data across.

`SIGNING_IDENTITY` is optional; set it to codesign the bundle. Notarisation and the
full signing recipe are in [`installer-mac/SIGNING.md`](installer-mac/SIGNING.md).

**Known local-build blocker:** PyInstaller cannot complete under iCloud-synced
`~/Desktop/Documents` — site-packages read as `dataless` and reads time out
(`Errno 60`). Build from a non-synced path (`~/build/…`, `/tmp`) or let CI do it.

## Source DMG

```bash
APP_VERSION=1.5.12 ./installer-mac/build-dmg.sh
```

The drag target is the `EasyOKAPI` **folder**, not the bare `.app` — `setup.sh`
installs the source tree into `code/` beside the app, mirroring
`$PROGRAMFILES64\EasyOKAPI` on Windows.

## Both builders also stage

- `uninstall.command` + `static/okapi.png` (its dialog icon) in the DMG root.
- `Legal/License Agreement.txt` and the privacy notice, rendered from `legal/`.
  macOS drag-to-install has no licence page, so the agreement must sit in the
  window the user drags from.

## Troubleshooting

- Script not executable: `chmod +x ./installer-mac/build-dmg-frozen.sh`
- `❌ APP_VERSION is not set` — export it: `APP_VERSION=1.5.12 ./installer-mac/…`
- `❌ Frozen bundle not found at dist/EasyOKAPI` — run `python tools/package.py --encode` first.

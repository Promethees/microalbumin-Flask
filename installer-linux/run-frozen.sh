#!/bin/bash
# run-frozen.sh — launcher for the no-source (PyInstaller) Linux build.
# No sudo, pyenv, or venv: the frozen binary is self-contained and creates its
# own per-user data dir (~/.local/share/EasyOKAPI) on first run. Loopback alias
# avoids editing /etc/hosts.
exec /opt/EasyOKAPI/EasyOKAPI/EasyOKAPI --port 5099 --alias 127.0.0.1

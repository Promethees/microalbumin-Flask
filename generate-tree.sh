#!/usr/bin/env bash
# ------------------------------------------------------------
# generate-tree.sh – current = root files only | dedup fixed
#   • NO hidden (dot) files/folders unless listed explicitly
#   • NO stray '.' line in the output
#   • Works on macOS, Linux, Git‑Bash – set -u safe
# ------------------------------------------------------------

set -euo pipefail

TARGET_ROOTS=()
DEPTH=""

# ---------- parse args ----------
while [[ $# -gt 0 ]]; do
  case $1 in
    -L|--max-depth)
      DEPTH="-L $2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./generate-tree.sh [-L <depth>] [current folder1 folder2 ...]
  current → only files in repo root (e.g. README.md)
  folder  → full tracked tree of that folder
  • Hidden (dot) items are ignored unless listed explicitly
EOF
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      TARGET_ROOTS+=("$1")
      shift
      ;;
  esac
done

# Default: whole repo
[[ ${#TARGET_ROOTS[@]} -eq 0 ]] && TARGET_ROOTS=(".")

# ---------- expand "current" ----------
EXPANDED=()
for item in "${TARGET_ROOTS[@]}"; do
  if [[ "$item" == "current" ]]; then
    # root files only – skip dot files
    while IFS= read -r file; do
      [[ -f "$file" && "$file" != .* ]] && EXPANDED+=("$file")
    done < <(git ls-files | grep -E '^[^/]+$' || true)
  else
    EXPANDED+=("$item")
  fi
done

# ---------- deduplicate (safe, robust) ----------
UNIQUE=()
for candidate in "${EXPANDED[@]}"; do
  is_duplicate=0
  for existing in "${UNIQUE[@]+"${UNIQUE[@]}"}"; do
    [[ "$candidate" == "$existing" ]] && is_duplicate=1 && break
  done
  (( is_duplicate == 0 )) && UNIQUE+=("$candidate")
done
EXPANDED=("${UNIQUE[@]}")

# ---------- validate existence ----------
VALID=()
for p in "${EXPANDED[@]}"; do
  if [[ -e "$p" ]]; then
    VALID+=("$p")
  else
    echo "Warning: '$p' not found – skipping." >&2
  fi
done
EXPANDED=("${VALID[@]}")

# ---------- collect tracked paths ----------
TMP_INPUT=$(mktemp)
TMP_TREE=$(mktemp)
trap 'rm -f "$TMP_INPUT" "$TMP_TREE"' EXIT

{
  for root in "${EXPANDED[@]}"; do
    if [[ -f "$root" ]]; then
      echo "$root"
    elif [[ -d "$root" ]]; then
      # exclude hidden items inside folders
      git ls-files --full-name "$root" 2>/dev/null |
        grep -v '/\.' || true
    fi
  done
} | sort -u > "$TMP_INPUT"

# ---------- prefix paths with root ----------
awk -v roots="${EXPANDED[*]}" '
BEGIN { split(roots, a, " "); for(i in a) r[a[i]]=1 }
{
  for (k in r) {
    if (system("[ -d \"" k "\" ]") == 0) {
      if ($0 == k || index($0, k "/") == 1) {
        sub("^" k "/", "")
        print k "/" $0
        next
      }
    }
  }
  print
}
' "$TMP_INPUT" > "$TMP_TREE"

# ---------- build tree ----------
# NOTE: we **do NOT** write a fake "." line – tree will treat the
# prefixed paths as separate top‑level entries.
tree -a --charset=ascii --noreport $DEPTH --fromfile "$TMP_TREE" |
  # Remove any stray "." line that tree might emit
  grep -v '^\* \.$' |
  sed -E '
    s|^\* \[([^]/]+)/(.*)\]$|* [\2](./\1/\2)|;
    s|^\* \[([^]/]+)/\]$|* [\1/](./\1/)|;
    s|^\* \[([^]/]+)\]$|* [\1](./\1)|;
  ' > "${TMP_TREE}.md"

# ---------- output ----------
cat <<EOF
# Project Structure (Git-tracked only)

\`\`\`markdown
$(cat "${TMP_TREE}.md")
\`\`\`
EOF
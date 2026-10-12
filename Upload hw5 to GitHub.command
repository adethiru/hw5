#!/bin/bash
# Double-click: publishes Homework 5 as a PUBLIC GitHub repo (Problem 11) using GitHub's web API
# (no git / developer tools needed). Safe to run again - it updates files that changed.
#  1. builds a clean copy in "upload to GitHub/hw5" (no .env, .venv, node_modules, caches)
#  2. refuses to continue if your real API key appears anywhere in that copy
#  3. creates the repo if it doesn't exist and makes sure it is public
#  4. writes output/github_url.txt and uploads every file
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
exec > >(tee "$ROOT/upload_log.txt") 2>&1
say()  { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }
fail() { printf "\n\033[31m✖ %s\033[0m\n" "$1"; read -n1 -rp "Press any key to close…"; exit 1; }
echo "Upload started $(date)"

# --- deliverables check ----------------------------------------------------
say "Checking deliverables"
MISSING=""
for f in AI_prompts.md requirements.txt .env.example .gitignore .mcp.json README.md \
         data/campus_customs.db data/campus_customs_new.db mcp_server/server.py mcp_server/README.md \
         backend/main.py backend/models.py backend/prompts/boss.md backend/prompts/inventory.md \
         backend/prompts/accounting.md backend/prompts/facilities.md backend/prompts/customer_service.md \
         frontend/package.json output/harness.md output/mcp_smoke.json output/desk_tickets.html \
         output/design.md output/resolved_tickets.json output/resolved_board.html output/audit_trail.json; do
  [ -e "$f" ] && echo "  ✓ $f" || { echo "  ✖ $f  (missing)"; MISSING="$MISSING $f"; }
done
if [ -n "$MISSING" ]; then
  printf "\n⚠️  Missing:%s\n   You can upload now and run this again after finishing them.\n" "$MISSING"
  read -rp "Upload anyway? (y/N) " A; [ "$A" = "y" ] || [ "$A" = "Y" ] || fail "Stopped. Nothing uploaded."
fi

# --- repo + token ------------------------------------------------------------
DEFAULT_REPO="adethiru/hw5"
read -rp "GitHub repo (owner/name) [press Return for $DEFAULT_REPO]: " REPO
REPO="${REPO:-$DEFAULT_REPO}"; REPO="${REPO#https://github.com/}"; REPO="${REPO%.git}"
URL="https://github.com/$REPO"

for attempt in 1 2 3; do
  echo "Paste your GitHub token (starts with ghp_ or github_pat_, needs 'repo' scope) and press Return."
  echo "Nothing shows while pasting — that's normal:"
  read -rs TOKEN; echo
  TOKEN=$(printf "%s" "$TOKEN" | tr -d '[:space:]')
  case "$TOKEN" in ghp_*|github_pat_*) ;; *) echo "✖ That doesn't look like a GitHub token."; TOKEN=""; continue;; esac
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" https://api.github.com/user)
  [ "$CODE" = "200" ] && { echo "✓ Token accepted"; break; }
  echo "✖ GitHub rejected that token (HTTP $CODE)."; TOKEN=""
done
[ -n "$TOKEN" ] || fail "No valid token."
AUTH="Authorization: Bearer $TOKEN"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "https://api.github.com/repos/$REPO")
if [ "$CODE" = "404" ]; then
  say "Creating public repo $REPO"
  NAME="${REPO#*/}"
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "$AUTH" -H "Content-Type: application/json" \
         -d "{\"name\":\"$NAME\",\"private\":false,\"description\":\"Campus Customs multi-agent operations (MCP + PydanticAI + FastAPI + React)\"}" \
         https://api.github.com/user/repos)
  [ "$CODE" = "201" ] || fail "Could not create repo (HTTP $CODE). Create an empty PUBLIC repo named $NAME on github.com, then run again."
  sleep 2
fi
# make sure it's public
curl -s -o /dev/null -X PATCH -H "$AUTH" -H "Content-Type: application/json" -d '{"private":false}' "https://api.github.com/repos/$REPO"

# --- github_url.txt + clean staging copy ---------------------------------------
printf "%s\n" "$URL" > output/github_url.txt
say "Building clean copy in 'upload to GitHub/hw5'"
STAGE="$ROOT/upload to GitHub/hw5"
rm -rf "$STAGE"; mkdir -p "$STAGE"
rsync -a \
  --exclude '.env' --exclude '.venv/' --exclude 'node_modules/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.DS_Store' --exclude 'frontend/dist/' --exclude '/campus_customs.db' --exclude 'upload to GitHub/' \
  --exclude 'upload_log.txt' --exclude '*.tmp' --exclude 'output/*.corrupt-*.json' \
  "$ROOT/" "$STAGE/"

# --- secret guard ---------------------------------------------------------------
[ -e "$STAGE/.env" ] && fail ".env ended up in the upload copy - refusing."
KEY=""
for envf in "$ROOT/.env" "$ROOT/../.env"; do
  [ -f "$envf" ] && KEY=$(grep -m1 '^PORTKEY_API_KEY=' "$envf" | cut -d= -f2- | tr -d '"'"'"' [:space:]') && [ -n "$KEY" ] && break
done
if [ -n "$KEY" ] && grep -rqF -- "$KEY" "$STAGE"; then
  grep -rlF -- "$KEY" "$STAGE" | sed 's/^/   /'
  fail "Your real PORTKEY_API_KEY appears in the files above - refusing to upload."
fi
echo "✓ No .env and no API key in the upload copy"

# --- upload ---------------------------------------------------------------------
say "Uploading to $URL"
cd "$STAGE" || exit 1
API="https://api.github.com/repos/$REPO/contents"
OK=0; FAIL=0; TMP=$(mktemp)
while IFS= read -r -d '' f; do
  path="${f#./}"
  enc=$(printf "%s" "$path" | sed 's/ /%20/g')
  sha=$(curl -s -H "$AUTH" "$API/$enc" | grep -m1 '"sha"' | sed -E 's/.*"sha": *"([^"]+)".*/\1/')
  { printf '{"message":"Add %s","content":"' "$path"
    base64 -i "$f" | tr -d '\n'
    printf '"'
    [ -n "$sha" ] && printf ',"sha":"%s"' "$sha"
    printf '}'; } > "$TMP"
  code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "$AUTH" -H "Content-Type: application/json" --data-binary @"$TMP" "$API/$enc")
  if [ "$code" = "200" ] || [ "$code" = "201" ]; then OK=$((OK+1)); echo "  ✓ $path"
  else FAIL=$((FAIL+1)); echo "  ✖ $path (HTTP $code)"; fi
done < <(find . -type f -print0 | sort -z)
rm -f "$TMP"

echo
echo "Uploaded $OK files, $FAIL failed."
VIS=$(curl -s -H "$AUTH" "https://api.github.com/repos/$REPO" | grep -m1 '"private"' | tr -d ' ,')
[ "$VIS" = '"private":false' ] && echo "✓ Repo is PUBLIC" || echo "⚠️  Could not confirm the repo is public — check Settings → General → Danger Zone."
printf "%s" "$URL" | pbcopy 2>/dev/null
echo "Submit on Canvas: $URL   (copied to clipboard; also saved in output/github_url.txt)"
read -n1 -rp "Press any key to close…"

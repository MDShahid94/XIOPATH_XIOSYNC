#!/bin/bash
# ==============================================================================
# Antigravity — Git History Secret Purge
# ==============================================================================
# Removes .env, data/.vault_key, data/secrets.json, data/api_keys.json from
# ALL git history.  This is a destructive operation: all commits are rewritten.
#
# Prerequisites:
#   pip install git-filter-repo
#
# After running:
#   1. Force-push:  git push --force --all
#   2. All collaborators MUST re-clone the repository.
# ==============================================================================

set -euo pipefail

echo "⚠️  This will rewrite ALL git history to remove sensitive files."
echo "   All collaborators will need to re-clone after this."
echo ""
read -p "Continue? (y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

if ! command -v git-filter-repo &> /dev/null; then
    echo "❌ git-filter-repo not found. Install with: pip install git-filter-repo"
    exit 1
fi

echo "🔒 Purging sensitive files from git history..."
git filter-repo --invert-paths \
    --path .env \
    --path data/.vault_key \
    --path data/secrets.json \
    --path data/api_keys.json \
    --force

echo ""
echo "✅ Sensitive files purged from git history."
echo ""
echo "Next steps:"
echo "  1. Revoke the leaked GitHub PAT at https://github.com/settings/tokens"
echo "  2. Regenerate data/.vault_key (python -m core.key_rotation rotate)"
echo "  3. Force-push: git push --force --all"
echo "  4. Notify all collaborators to re-clone."

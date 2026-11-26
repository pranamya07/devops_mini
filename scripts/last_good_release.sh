#!/usr/bin/env bash
# Print the last release tag (e.g. v1.1.0) that deployed to production AND passed
# its post-deployment checks, according to GitHub's deployment history.
# Prints nothing if there is none yet (the very first release).
#
# Usage (in GitHub Actions, with GH_TOKEN set):
#   scripts/last_good_release.sh v1.2.0     # skip the release being deployed now
#
# Falls back to the previous version tag in git if no deployment history exists.
set -euo pipefail

current="${1:-}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
release_tag='^v[0-9]+\.[0-9]+\.[0-9]+$'

# Production deployments, newest first, that were made from a release tag.
deployments=$(gh api "repos/$repo/deployments?environment=production&per_page=100" \
  --jq ".[] | select(.ref | test(\"$release_tag\")) | \"\(.id) \(.ref)\"" 2>/dev/null || true)

while read -r id ref; do
  [[ -z "$id" || "$ref" == "$current" ]] && continue
  state=$(gh api "repos/$repo/deployments/$id/statuses?per_page=1" --jq '.[0].state // ""')
  if [[ "$state" == "success" ]]; then
    echo "$ref"
    exit 0
  fi
done <<< "$deployments"

# No successful deployment recorded: use the version tag just below the current one.
git tag --list 'v*.*.*' --sort=-v:refname | grep -E "$release_tag" \
  | awk -v current="$current" 'found { print; exit } $0 == current { found = 1 }'

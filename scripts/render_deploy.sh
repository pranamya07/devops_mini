#!/usr/bin/env bash
# Ask Render to deploy one exact image version, using the service's deploy hook.
#
# Usage:
#   RENDER_DEPLOY_HOOK_URL=https://api.render.com/deploy/srv-...?key=... \
#     scripts/render_deploy.sh ghcr.io/pranamya07/devops_mini:1.1.0
#
# Render only accepts an image from the same repository as the one in the
# service's settings; only the tag may differ.
set -euo pipefail

image="${1:?usage: render_deploy.sh <image>:<tag>}"
hook="${RENDER_DEPLOY_HOOK_URL:?Set RENDER_DEPLOY_HOOK_URL (the Render deploy hook URL)}"

# The image reference must be URL-encoded inside the query string.
encoded=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$image")
separator='?'
[[ "$hook" == *\?* ]] && separator='&'

echo "Asking Render to deploy $image"
response=$(curl --fail-with-body --silent --show-error --max-time 60 \
  --request POST "${hook}${separator}imgURL=${encoded}")
echo "Render accepted the deploy: $response"

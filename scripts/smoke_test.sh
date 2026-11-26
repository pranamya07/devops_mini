#!/usr/bin/env bash
# Smoke test the real Docker image with Docker Compose and PostgreSQL:
#   1. start API + database and wait until both are healthy
#   2. create a task through the API
#   3. restart the containers
#   4. check the task is still there (data persisted in the volume)
#
# Usage:
#   API_IMAGE=taskapi:ci ./scripts/smoke_test.sh   # test an image that is already built (CI)
#   ./scripts/smoke_test.sh                        # build from the Dockerfile first
# Set API_PORT if 8000 is busy, e.g. API_PORT=8001.
set -euo pipefail

cd "$(dirname "$0")/.."

export API_PORT="${API_PORT:-8000}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-smoke-test-only}"
BASE_URL="http://localhost:${API_PORT}"
COMPOSE=(docker compose --project-name taskapi-smoke)

if [[ -n "${API_IMAGE:-}" ]]; then
  BUILD_FLAG=--no-build
else
  export API_IMAGE=taskapi:local
  BUILD_FLAG=--build
fi

cleanup() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    echo "::group::Container logs (smoke test failed)"
    "${COMPOSE[@]}" logs --no-color || true
    echo "::endgroup::"
  fi
  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  exit $status
}
trap cleanup EXIT

step() { printf '\n==> %s\n' "$*"; }

step "Starting API ($API_IMAGE) and PostgreSQL"
# Only the API and its database; the monitoring stack isn't needed here.
"${COMPOSE[@]}" up -d "$BUILD_FLAG" --wait --wait-timeout 120 api

step "Checking /health"
curl -fsS "$BASE_URL/health"
echo

step "Checking the container is not running as root"
uid=$("${COMPOSE[@]}" exec -T api id -u)
echo "api container runs as uid $uid"
[[ "$uid" != "0" ]]

step "Creating a task"
task=$(curl -fsS -X POST "$BASE_URL/api/v1/tasks" \
  -H 'content-type: application/json' \
  -d '{"title": "Smoke test task", "priority": "high"}')
echo "$task"
task_id=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])' <<<"$task")

step "Restarting both containers"
"${COMPOSE[@]}" restart
"${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 120 api

step "Checking task $task_id survived the restart"
curl -fsS "$BASE_URL/api/v1/tasks/$task_id" | tee /dev/stderr | grep -q '"Smoke test task"'
echo

step "Checking Docker reports the API container as healthy"
health=$(docker inspect --format '{{.State.Health.Status}}' "$("${COMPOSE[@]}" ps -q api)")
echo "health: $health"
[[ "$health" == "healthy" ]]

step "Smoke test passed"

"""Send realistic traffic to the API so the Grafana dashboard has something to show.

Mostly normal CRUD calls, plus a few 404s and 422s (client errors).

Usage:
    python scripts/generate_traffic.py                       # localhost:8000 for 60s
    python scripts/generate_traffic.py --duration 300 --rps 10
    python scripts/generate_traffic.py --base-url https://your-app.onrender.com

Uses only the Python standard library.
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from collections import Counter

PRIORITIES = ["low", "medium", "high"]
STATUSES = ["todo", "in_progress", "done"]


def call(base_url, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base_url + path, data=data, method=method, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        return error.code, None


def one_request(base_url, task_ids):
    roll = random.random()
    if roll < 0.25 or not task_ids:
        status, task = call(
            base_url,
            "POST",
            "/api/v1/tasks",
            {
                "title": f"Load test task {random.randint(1, 9999)}",
                "priority": random.choice(PRIORITIES),
            },
        )
        if status == 201:
            task_ids.append(task["id"])
        return "POST /tasks", status
    if roll < 0.55:
        return "GET /tasks", call(base_url, "GET", "/api/v1/tasks?limit=20")[0]
    if roll < 0.75:
        task_id = random.choice(task_ids)
        return "GET /tasks/{id}", call(base_url, "GET", f"/api/v1/tasks/{task_id}")[0]
    if roll < 0.85:
        task_id = random.choice(task_ids)
        body = {"status": random.choice(STATUSES)}
        return "PATCH /tasks/{id}", call(base_url, "PATCH", f"/api/v1/tasks/{task_id}", body)[0]
    if roll < 0.90 and len(task_ids) > 5:
        task_id = task_ids.pop(0)
        return "DELETE /tasks/{id}", call(base_url, "DELETE", f"/api/v1/tasks/{task_id}")[0]
    if roll < 0.95:
        return "GET missing task", call(base_url, "GET", "/api/v1/tasks/999999")[0]
    return "POST invalid task", call(base_url, "POST", "/api/v1/tasks", {"title": ""})[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration", type=int, default=60, help="seconds to run")
    parser.add_argument("--rps", type=float, default=5, help="requests per second")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    results = Counter()
    task_ids = []
    end = time.monotonic() + args.duration
    print(f"Sending ~{args.rps} req/s to {base_url} for {args.duration}s (Ctrl+C to stop)")
    try:
        while time.monotonic() < end:
            try:
                name, status = one_request(base_url, task_ids)
            except (urllib.error.URLError, TimeoutError) as error:
                name, status = "connection error", type(error).__name__
            results[f"{name} -> {status}"] += 1
            time.sleep(1 / args.rps)
    except KeyboardInterrupt:
        pass

    print(f"\n{sum(results.values())} requests sent:")
    for line, count in sorted(results.items()):
        print(f"  {count:5d}  {line}")


if __name__ == "__main__":
    main()

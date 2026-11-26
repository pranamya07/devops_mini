"""Unit tests for the release shell scripts:
- render_deploy.sh asks Render to deploy one exact image tag
- last_good_release.sh picks the version to roll back to
"""

import json
import os
import subprocess
import urllib.parse

import pytest

from tests.unit.conftest import SCRIPTS

IMAGE = "ghcr.io/pranamya07/devops_mini"


def run_script(name, *args, env=None, cwd=None):
    return subprocess.run(
        ["bash", str(SCRIPTS / name), *args],
        env={**os.environ, **(env or {})},
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class TestRenderDeploy:
    def test_sends_the_exact_image_to_the_deploy_hook(self, fake_server):
        fake_server.routes[("POST", "/deploy/srv-test")] = lambda _: (200, {"id": "dep-1"})

        result = run_script(
            "render_deploy.sh",
            f"{IMAGE}:1.1.0",
            env={"RENDER_DEPLOY_HOOK_URL": f"{fake_server.url}/deploy/srv-test?key=abc"},
        )

        assert result.returncode == 0, result.stderr
        [(method, path, _)] = fake_server.requests
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        assert method == "POST"
        assert query == {"key": ["abc"], "imgURL": [f"{IMAGE}:1.1.0"]}
        assert "imgURL=ghcr.io%2Fpranamya07%2Fdevops_mini%3A1.1.0" in path

    def test_fails_when_render_rejects_the_deploy(self, fake_server):
        fake_server.routes[("POST", "/deploy/srv-test")] = lambda _: (400, {"error": "bad image"})

        result = run_script(
            "render_deploy.sh",
            f"{IMAGE}:1.1.0",
            env={"RENDER_DEPLOY_HOOK_URL": f"{fake_server.url}/deploy/srv-test?key=abc"},
        )

        assert result.returncode != 0

    def test_fails_without_a_deploy_hook(self):
        result = run_script(
            "render_deploy.sh", f"{IMAGE}:1.1.0", env={"RENDER_DEPLOY_HOOK_URL": ""}
        )

        assert result.returncode != 0
        assert "RENDER_DEPLOY_HOOK_URL" in result.stderr


@pytest.fixture
def release_repo(tmp_path):
    """A git repo with release tags, plus a fake `gh` CLI serving deployment history."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True)
    for tag in ["v1.0.0", "v1.1.0", "v1.2.0", "v1.3.0-rc1"]:
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", tag], cwd=repo, check=True)
        subprocess.run([*git, "tag", tag], cwd=repo, check=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    # Replies like `gh api ... --jq ...` would, from FAKE_DEPLOYMENTS (newest first).
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, re, sys\n"
        "history = json.loads(os.environ.get('FAKE_DEPLOYMENTS', '[]'))\n"
        "path = sys.argv[2]\n"
        "match = re.search(r'deployments/(\\d+)/statuses', path)\n"
        "if match:\n"
        "    print(next(d['state'] for d in history if d['id'] == int(match.group(1))))\n"
        "else:\n"
        "    for d in history:\n"
        "        if re.fullmatch(r'v\\d+\\.\\d+\\.\\d+', d['ref']):\n"
        "            print(d['id'], d['ref'])\n"
    )
    fake_gh.chmod(0o755)

    def last_good(current, deployments=()):
        result = run_script(
            "last_good_release.sh",
            current,
            cwd=repo,
            env={
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "GITHUB_REPOSITORY": "owner/repo",
                "FAKE_DEPLOYMENTS": json.dumps(list(deployments)),
            },
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    return last_good


class TestLastGoodRelease:
    def test_skips_a_release_that_failed_its_checks(self, release_repo):
        history = [
            {"id": 3, "ref": "v1.2.0", "state": "failure"},
            {"id": 2, "ref": "v1.1.0", "state": "success"},
            {"id": 1, "ref": "v1.0.0", "state": "success"},
        ]
        assert release_repo("v1.2.1", history) == "v1.1.0"

    def test_skips_the_release_being_deployed_now(self, release_repo):
        history = [
            {"id": 3, "ref": "v1.2.0", "state": "in_progress"},
            {"id": 2, "ref": "v1.1.0", "state": "success"},
        ]
        assert release_repo("v1.2.0", history) == "v1.1.0"

    def test_ignores_deployments_not_made_from_a_release_tag(self, release_repo):
        history = [
            {"id": 4, "ref": "main", "state": "success"},
            {"id": 2, "ref": "v1.0.0", "state": "success"},
        ]
        assert release_repo("v1.2.0", history) == "v1.0.0"

    def test_falls_back_to_previous_git_tag_without_history(self, release_repo):
        assert release_repo("v1.2.0") == "v1.1.0"

    def test_first_release_has_nothing_to_roll_back_to(self, release_repo):
        assert release_repo("v1.0.0") == ""

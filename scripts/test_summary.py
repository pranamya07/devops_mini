"""Turn pytest's JUnit XML into a Markdown summary for the GitHub Actions run page.

Usage: python scripts/test_summary.py reports/junit.xml >> "$GITHUB_STEP_SUMMARY"
"""

import sys
import xml.etree.ElementTree as ET


def summarize(junit_path: str) -> str:
    # Parses the report pytest just wrote in this job, not untrusted input.
    root = ET.parse(junit_path).getroot()  # noqa: S314
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    counts = {key: int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")}
    passed = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    failed = counts["failures"] + counts["errors"]

    lines = [
        "## Test results",
        "",
        "| Result | Total | Passed | Failed | Skipped | Time |",
        "|---|---|---|---|---|---|",
        f"| {'✅ passed' if failed == 0 else '❌ failed'} | {counts['tests']} | {passed} "
        f"| {failed} | {counts['skipped']} | {float(suite.get('time', 0)):.1f}s |",
    ]

    failing = [
        f"- `{case.get('classname')}.{case.get('name')}`"
        for case in suite.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if failing:
        lines += ["", "### Failing tests", "", *failing]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(summarize(sys.argv[1]))

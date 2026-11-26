"""Container health check: exits 0 if the API's /health returns 200.

Used by the Dockerfile HEALTHCHECK, because the slim image has no curl.
"""

import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    port = os.getenv("PORT", "8000")
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, OSError):
        return 1


if __name__ == "__main__":
    sys.exit(main())

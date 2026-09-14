#!/usr/bin/env python3
"""Launch the interactive God's Eye 3D Scene Explorer in the default browser.

Usage:
    python viewer/serve.py [JOB_ID]
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = REPO_ROOT / "outputs"


def get_latest_job_id() -> str | None:
    if not OUTPUTS_DIR.is_dir():
        return None
    jobs = sorted(
        [d for d in OUTPUTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return jobs[0].name if jobs else None


def main() -> None:
    job_id = sys.argv[1] if len(sys.argv) > 1 else get_latest_job_id()
    if not job_id:
        print("No completed jobs found in outputs/.")
        sys.exit(1)

    port = 8000
    handler = http.server.SimpleHTTPRequestHandler

    # Allow fast restart on same port
    socketserver.TCPServer.allow_reuse_address = True

    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://localhost:{port}/viewer/?job={job_id}"
            print(f"\n=======================================================")
            print(f" God's Eye 3D Scene Explorer")
            print(f" Serving Job: {job_id}")
            print(f" URL:         {url}")
            print(f"=======================================================\n")
            webbrowser.open(url)
            print("Press Ctrl+C to stop the server.\n")
            httpd.serve_forever()
    except OSError:
        # If port 8000 is occupied, try 8080
        port = 8080
        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://localhost:{port}/viewer/?job={job_id}"
            print(f"\nGod's Eye 3D Scene Explorer running at: {url}\n")
            webbrowser.open(url)
            print("Press Ctrl+C to stop the server.\n")
            httpd.serve_forever()


if __name__ == "__main__":
    main()

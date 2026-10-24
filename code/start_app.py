"""Run from any working directory: python path/to/code/start_app.py --open."""

import argparse
from pathlib import Path

from ghosttrace.server import serve


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start GhostTrace locally")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    project = Path(__file__).resolve().parent.parent
    demo = project / "code" / "examples" / "demo" / "deletion_requests.csv"
    if not demo.is_file():
        from make_demo import generate
        generate(demo.parent)
    serve(project=project, port=args.port, open_browser=args.open)

"""Entrypoint: python3 -m matutino"""

import argparse
import os
import sys

from . import VERSION


def main(argv=None):
    p = argparse.ArgumentParser(prog="matutino",
                                description="Turn RSS feeds into a daily newspaper (web + EPUB).")
    p.add_argument("--data", default=os.environ.get("MATUTINO_DATA", "data"),
                   help="folder for the database (never the exFAT drive); issues too unless --issues")
    p.add_argument("--epub-dir", default=os.environ.get("MATUTINO_EPUB_DIR", ""),
                   help="Kavita library folder to file each EPUB in (optional)")
    p.add_argument("--issues", default=os.environ.get("MATUTINO_ISSUES", ""),
                   help="folder for printed issues (default: <data>/issues); may be another drive")
    p.add_argument("--host", default=os.environ.get("MATUTINO_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MATUTINO_PORT", "8771")))
    p.add_argument("--print-now", action="store_true", help="print one issue, report, and exit")
    p.add_argument("--version", action="version", version="Matutino " + VERSION)
    a = p.parse_args(argv)

    from . import server
    if a.print_now:
        app = server.App(a.data, a.epub_dir, a.issues)
        report = app.builder.run("command line")
        return 0 if report and report.get("ok") else 1
    return server.serve(a.data, a.epub_dir, a.host, a.port, issues_dir=a.issues)


if __name__ == "__main__":
    sys.exit(main())

"""CLI entry point for commit-intelligence."""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(
        prog="commit_intelligence",
        description="Commit Intelligence for GitHub orgs",
    )
    sub = parser.add_subparsers(dest="command")

    # scan
    p_scan = sub.add_parser("scan", help="Scan repos for commits")
    p_scan.add_argument("--org", required=True, help="GitHub org name")
    p_scan.add_argument("--token", help="GitHub PAT (or set GITHUB_TOKEN env)")
    p_scan.add_argument("--months", type=int, default=6, help="Months of history (default: 6)")

    # scan-local
    p_local = sub.add_parser("scan-local", help="Scan local git repos on disk")
    p_local.add_argument("--path", required=True, help="Directory containing git repos")
    p_local.add_argument("--org", default="local", help="Org label for display (default: local)")
    p_local.add_argument("--since", help="Only include commits after this date (YYYY-MM-DD)")

    # backfill-sizes
    p_sizes = sub.add_parser("backfill-sizes", help="Extract commit sizes from local repos")
    p_sizes.add_argument("--path", required=True, help="Directory containing git repos")

    # deduplicate-authors
    sub.add_parser("deduplicate-authors", help="Heuristic author deduplication")

    # analyze
    sub.add_parser("analyze", help="Classify commits with heuristics")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dash.add_argument("--output", default="docs/", help="Output directory (default: docs/)")

    # run (all-in-one via GitHub API)
    p_run = sub.add_parser("run", help="Scan + analyze + deduplicate + dashboard (GitHub API)")
    p_run.add_argument("--org", required=True, help="GitHub org name")
    p_run.add_argument("--token", help="GitHub PAT (or set GITHUB_TOKEN env)")
    p_run.add_argument("--months", type=int, default=6, help="Months of history (default: 6)")
    p_run.add_argument("--output", default="docs/", help="Dashboard output directory")

    # run-local (all-in-one from local git repos)
    p_runl = sub.add_parser("run-local", help="Scan + analyze + deduplicate + backfill + dashboard (local repos)")
    p_runl.add_argument("--path", required=True, help="Directory containing git repos")
    p_runl.add_argument("--org", default="local", help="Org label for display (default: local)")
    p_runl.add_argument("--since", help="Only include commits after this date (YYYY-MM-DD)")
    p_runl.add_argument("--output", default="docs/", help="Dashboard output directory")

    args = parser.parse_args()

    if args.command == "scan":
        from .scanner import scan
        scan(args.org, token=args.token, months=args.months)

    elif args.command == "scan-local":
        from .scanner import scan_local
        scan_local(args.path, org_name=args.org, since_date=args.since)

    elif args.command == "deduplicate-authors":
        from .analyzer import deduplicate_authors
        deduplicate_authors()

    elif args.command == "backfill-sizes":
        from .scanner import backfill_sizes
        backfill_sizes(args.path)

    elif args.command == "analyze":
        from .analyzer import analyze
        analyze()

    elif args.command == "dashboard":
        from .dashboard import generate
        generate(output_dir=args.output)

    elif args.command == "run":
        from .scanner import scan
        from .analyzer import analyze, deduplicate_authors
        from .dashboard import generate

        scan(args.org, token=args.token, months=args.months)
        analyze()
        deduplicate_authors()
        generate(output_dir=args.output)

    elif args.command == "run-local":
        from .scanner import scan_local, backfill_sizes
        from .analyzer import analyze, deduplicate_authors
        from .dashboard import generate

        scan_local(args.path, org_name=args.org, since_date=args.since)
        analyze()
        deduplicate_authors()
        backfill_sizes(args.path)
        generate(output_dir=args.output)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

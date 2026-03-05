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

    # analyze
    p_analyze = sub.add_parser("analyze", help="Classify commits with Ollama")
    p_analyze.add_argument("--model", default="qwen2.5:3b", help="Ollama model (default: qwen2.5:3b)")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Generate HTML dashboard")
    p_dash.add_argument("--output", default="docs/", help="Output directory (default: docs/)")

    # run (all-in-one: scan + analyze + dashboard)
    p_run = sub.add_parser("run", help="Scan + analyze + dashboard")
    p_run.add_argument("--org", required=True, help="GitHub org name")
    p_run.add_argument("--token", help="GitHub PAT (or set GITHUB_TOKEN env)")
    p_run.add_argument("--months", type=int, default=6, help="Months of history (default: 6)")
    p_run.add_argument("--model", default="qwen2.5:3b", help="Ollama model (default: qwen2.5:3b)")
    p_run.add_argument("--output", default="docs/", help="Dashboard output directory")

    args = parser.parse_args()

    if args.command == "scan":
        from .scanner import scan
        scan(args.org, token=args.token, months=args.months)

    elif args.command == "analyze":
        from .analyzer import analyze
        analyze(model=args.model)

    elif args.command == "dashboard":
        from .dashboard import generate
        generate(output_dir=args.output)

    elif args.command == "run":
        from .scanner import scan
        from .analyzer import analyze
        from .dashboard import generate

        scan(args.org, token=args.token, months=args.months)
        analyze(model=args.model)
        generate(output_dir=args.output)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

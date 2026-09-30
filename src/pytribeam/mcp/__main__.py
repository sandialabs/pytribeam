from __future__ import annotations

import argparse

from pytribeam.mcp import server


def _main() -> None:
    parser = argparse.ArgumentParser(description="pytribeam MCP state inspection interface")
    parser.add_argument("command", choices=["list", "get", "diff"], nargs="?", default="list")
    parser.add_argument("--directory", default=None, help="State directory to inspect")
    parser.add_argument("--record", default=None, help="Record id to fetch")
    parser.add_argument("--before", default=None, help="Before record id for a diff")
    parser.add_argument("--after", default=None, help="After record id for a diff")
    args = parser.parse_args()

    if args.command == "list":
        print(server.list_states(args.directory))
        return
    if args.command == "get":
        if not args.record:
            raise SystemExit("--record is required for get")
        print(server.get_state(args.record, args.directory))
        return
    if args.command == "diff":
        if not args.before or not args.after:
            raise SystemExit("--before and --after are required for diff")
        print(server.diff_states(args.before, args.after, args.directory))
        return


if __name__ == "__main__":
    _main()

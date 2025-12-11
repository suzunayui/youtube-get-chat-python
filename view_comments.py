"""Print recent comments from comments.db."""
from __future__ import annotations

import argparse
import json

import chat_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Show recent YouTube live chat comments.")
    parser.add_argument(
        "--store-dir",
        help="Directory containing comments.db (defaults to current directory).",
        default=None,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of recent comments to show (max 500).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON objects instead of simple lines.",
    )
    args = parser.parse_args()

    chat_store.init_chat_store(args.store_dir)
    rows = chat_store.get_recent_comments(args.limit)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    for r in rows:
        print(f"{r['timestamp']} {r['author']}: {r['text']} ({r['kind']}) {r.get('amount_text') or ''}".strip())


if __name__ == "__main__":
    main()

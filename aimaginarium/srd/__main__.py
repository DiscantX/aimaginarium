"""``python -m aimaginarium.srd build [--db PATH] [--edition 2024]``"""

import argparse

from .store import DEFAULT_DB_PATH, DEFAULT_EDITION, build_database


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m aimaginarium.srd")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the SRD database from data/srd")
    build.add_argument("--db", default=str(DEFAULT_DB_PATH), help="output database path")
    build.add_argument("--edition", default=DEFAULT_EDITION)
    args = parser.parse_args()

    counts = build_database(args.db, edition=args.edition)
    for collection, count in counts.items():
        print(f"{collection:28} {count:5}")
    print(f"{'total':28} {sum(counts.values()):5}  ->  {args.db}")


if __name__ == "__main__":
    main()

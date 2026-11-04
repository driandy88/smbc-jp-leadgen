"""Cloud Run Job entrypoint: python -m app.jobs collect --run-id 12 | websearch --id 3"""

import argparse
import logging

from app.db import init_db
from app.services.collector import Collector


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--run-id", type=int, required=True)
    ws = sub.add_parser("websearch")
    ws.add_argument("--id", type=int, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    if args.cmd == "collect":
        Collector(args.run_id).run()
    elif args.cmd == "websearch":
        from app.services.webagent import Agent

        Agent(args.id).run()


if __name__ == "__main__":
    main()

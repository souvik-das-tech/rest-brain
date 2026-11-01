"""Start the REST API: python -m brain [--host 127.0.0.1] [--port 8787]  (or: python main.py)

Settings come from the command line, environment variables or a .env file next to this project
(see README.md). Real environment variables win over .env.
"""

from __future__ import annotations

import argparse
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from brain.paths import logs_dir
from brain.server import create_app
from brain.sessions import SessionManager

DEFAULT_MODEL = "gemini-3.8-flash-medium"


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="python -m brain", description="AGY CLI as a REST API")
    parser.add_argument("--host", default=env("BRAIN_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(env("BRAIN_PORT", "8787")))
    parser.add_argument("--model", default=env("BRAIN_MODEL", DEFAULT_MODEL), help="default AGY model")
    parser.add_argument("--username", default=env("BRAIN_USERNAME"), help="Basic auth username")
    parser.add_argument("--password", default=env("BRAIN_PASSWORD"), help="Basic auth password")
    parser.add_argument("--cors", default=env("BRAIN_CORS", ""), help='allowed browser origins, comma separated, or "*"')
    parser.add_argument("--max-sessions", type=int, default=int(env("BRAIN_MAX_SESSIONS", "10")))
    parser.add_argument("--idle-timeout", type=float, default=float(env("BRAIN_IDLE_TIMEOUT", "1800")),
                        help="seconds before an unused session is closed")
    parser.add_argument("--turn-timeout", type=float, default=float(env("BRAIN_TURN_TIMEOUT", "150")))
    args = parser.parse_args()

    handlers: list[logging.Handler] = [logging.StreamHandler(),
                                       RotatingFileHandler(logs_dir() / "brain.log", maxBytes=2_000_000,
                                                           backupCount=3, encoding="utf-8")]
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if bool(args.username) != bool(args.password):
        parser.error("set both BRAIN_USERNAME and BRAIN_PASSWORD (or neither)")
    if not args.username:
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            logging.warning("Listening on %s without Basic auth: anyone on the network can use your AGY account. "
                            "Set BRAIN_USERNAME and BRAIN_PASSWORD.", args.host)
        else:
            logging.info("Basic auth is off (BRAIN_USERNAME / BRAIN_PASSWORD not set).")

    manager = SessionManager(args.model, max_sessions=args.max_sessions, idle_timeout=args.idle_timeout,
                             turn_timeout=args.turn_timeout)
    cors = [o.strip() for o in args.cors.split(",") if o.strip()]
    app = create_app(manager, username=args.username, password=args.password, cors=cors)
    logging.info("Rest Brain on http://%s:%s  (docs: /docs)", args.host, args.port)
    # log_config=None: keep the handlers above (console + rotating file) for uvicorn's logs too.
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)


if __name__ == "__main__":
    main()

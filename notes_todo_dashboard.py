#!/usr/bin/env python3
"""FastAPI entrypoint for Notes Toolkit backend."""

from __future__ import annotations

import argparse
import os

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Notes Toolkit backend (FastAPI).")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--process-interval", type=int, default=int(os.environ.get("PROCESS_INTERVAL", "120")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ["PROCESS_INTERVAL"] = str(args.process_interval)
    uvicorn.run(
        "apps.backend.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()

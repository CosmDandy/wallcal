"""Entry point: `wallcal` or `python -m wallcal`."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="wallcal", description="Serve calendar wallpapers")
    parser.add_argument("--host", default=os.environ.get("WALLCAL_HOST", "0.0.0.0"))  # noqa: S104
    parser.add_argument("--port", type=int, default=int(os.environ.get("WALLCAL_PORT", "8000")))
    parser.add_argument("--reload", action="store_true")
    # Behind a reverse proxy every request otherwise logs the proxy's address.
    # uvicorn only rewrites the client from X-Forwarded-For for peers listed
    # here, and the default is nothing: an untrusted caller must not be able to
    # claim any address it likes. Set it to the proxy's address, or "*" when the
    # container is only reachable through that proxy.
    parser.add_argument(
        "--forwarded-allow-ips", default=os.environ.get("WALLCAL_TRUSTED_PROXY", "")
    )
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "wallcal.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=bool(args.forwarded_allow_ips),
        forwarded_allow_ips=args.forwarded_allow_ips or None,
        # We log our own line per request, with the timing and the size in it.
        access_log=False,
    )


if __name__ == "__main__":
    main()

import os

import uvicorn

from relay.chaos.app import create_chaos_app


def main() -> None:
    app = create_chaos_app(os.environ.get("CHAOS_VERIFY_SECRET") or None)
    uvicorn.run(
        app,
        host=os.environ.get("CHAOS_HOST", "127.0.0.1"),
        port=int(os.environ.get("CHAOS_PORT", "9000")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()

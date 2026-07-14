import uvicorn

from relay.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "relay.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        proxy_headers=True,
        log_level="warning",
    )


if __name__ == "__main__":
    main()

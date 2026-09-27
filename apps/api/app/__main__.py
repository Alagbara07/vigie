import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.listen_port(),
        log_level="info",
    )


if __name__ == "__main__":
    main()

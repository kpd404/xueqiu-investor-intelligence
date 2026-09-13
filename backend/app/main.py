from fastapi import FastAPI

from backend.app.api.router import api_router
from config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Thin read-only Intelligence API over observed effective evidence. "
            "Historical completeness is UNKNOWN; the API makes no causality or absence inference."
        ),
    )
    application.include_router(api_router)
    return application


app = create_app()

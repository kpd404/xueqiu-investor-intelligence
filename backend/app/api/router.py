from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.intelligence import router as intelligence_router
from backend.app.api.routes.intelligence_discovery import router as intelligence_discovery_router
from backend.app.api.routes.intelligence_feed import router as intelligence_feed_router
from backend.app.api.routes.intelligence_query import router as intelligence_query_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(intelligence_router)
api_router.include_router(intelligence_query_router)
api_router.include_router(intelligence_feed_router)
api_router.include_router(intelligence_discovery_router)

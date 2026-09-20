from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.intelligence import router as intelligence_router
from backend.app.api.routes.intelligence_attention_classification import (
    router as intelligence_attention_classification_router,
)
from backend.app.api.routes.intelligence_context import router as intelligence_context_router
from backend.app.api.routes.intelligence_discovery import router as intelligence_discovery_router
from backend.app.api.routes.intelligence_evolution import router as intelligence_evolution_router
from backend.app.api.routes.intelligence_feed import router as intelligence_feed_router
from backend.app.api.routes.intelligence_investor_product import (
    router as intelligence_investor_product_router,
)
from backend.app.api.routes.intelligence_narrative import router as intelligence_narrative_router
from backend.app.api.routes.intelligence_patterns import router as intelligence_patterns_router
from backend.app.api.routes.intelligence_product import router as intelligence_product_router
from backend.app.api.routes.intelligence_query import router as intelligence_query_router
from backend.app.api.routes.operations import router as operations_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(intelligence_attention_classification_router)
api_router.include_router(intelligence_router)
api_router.include_router(intelligence_query_router)
api_router.include_router(intelligence_feed_router)
api_router.include_router(intelligence_discovery_router)
api_router.include_router(intelligence_narrative_router)
api_router.include_router(intelligence_context_router)
api_router.include_router(intelligence_patterns_router)
api_router.include_router(intelligence_evolution_router)
api_router.include_router(intelligence_product_router)
api_router.include_router(intelligence_investor_product_router)
api_router.include_router(operations_router)

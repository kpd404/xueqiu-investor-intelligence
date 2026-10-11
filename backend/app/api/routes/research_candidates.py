"""Explicit user research writes; no generated intelligence writes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect

from backend.app.api.dependencies import _read_only_session
from database.session import SessionFactory
from intelligence.product.evidence import EvidenceUnavailable
from intelligence.product.research import AddResearch, EditResearch, ResearchService
from intelligence.product.research_schemas import ResearchList, ResearchView

router = APIRouter(prefix="/api/research-candidates", tags=["research-candidates"])


def get_research_service():
    with SessionFactory() as session:
        if not inspect(session.get_bind()).has_table("research_candidates"):
            raise HTTPException(503, "研究记录存储尚未安装；需要单独批准数据库升级，未自动迁移。")
    return ResearchService(SessionFactory, _read_only_session)


Service = Annotated[ResearchService, Depends(get_research_service)]


def execute(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (EvidenceUnavailable, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("", response_model=ResearchList)
def list_candidates(service: Service):
    return execute(service.list)


@router.post("", response_model=ResearchView)
def add_candidate(body: AddResearch, service: Service):
    return execute(lambda: service.add(body))


@router.get("/{candidate_id}", response_model=ResearchView)
def read_candidate(candidate_id: UUID, service: Service):
    return execute(lambda: service.read(candidate_id))


@router.patch("/{candidate_id}", response_model=ResearchView)
def edit_candidate(candidate_id: UUID, body: EditResearch, service: Service):
    return execute(lambda: service.edit(candidate_id, body))

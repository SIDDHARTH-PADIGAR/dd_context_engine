from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import text

from dd_context_engine.config import settings
from dd_context_engine.context.compiler import ContextAssemblyService
from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    ContextBundle,
    ContextRequest,
    EvidenceEnvelope,
    EvidenceSpan,
)
from dd_context_engine.storage.db import engine
from dd_context_engine.storage.postgres import (
    PostgresAssertionRepository,
    PostgresEvidenceRepository,
    PostgresWorkflowRepository,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


evidence_repo = PostgresEvidenceRepository()
assertion_repo = PostgresAssertionRepository()
workflow_repo = PostgresWorkflowRepository()
context_service = ContextAssemblyService(workflow_repo, assertion_repo, evidence_repo)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/v1/evidence", status_code=202)
async def ingest_evidence(envelope: EvidenceEnvelope) -> dict[str, object]:
    created = await evidence_repo.put_envelope(envelope)
    return {"source_id": str(envelope.source_id), "created": created}


@app.post("/v1/evidence/spans", status_code=202)
async def add_evidence_span(span: EvidenceSpan) -> dict[str, object]:
    created = await evidence_repo.put_span(span)
    return {"span_id": str(span.span_id), "created": created}


@app.post("/v1/assertions", status_code=202)
async def add_assertion(assertion: CommercialAssertion) -> dict[str, object]:
    created = await assertion_repo.put(assertion)
    return {"assertion_id": str(assertion.assertion_id), "created": created}


@app.post("/v1/context/compile", response_model=ContextBundle)
async def compile_context(request: ContextRequest) -> ContextBundle:
    return await context_service.build(request)


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": app.version, "checked_at": datetime.now(UTC).isoformat()}

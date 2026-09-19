from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from dd_context_engine.config import settings
from dd_context_engine.context.compiler import ContextAssemblyService
from dd_context_engine.domain.schemas import (
    CommercialAssertion,
    ContextBundle,
    ContextRequest,
    EvidenceEmbedding,
    EvidenceEnvelope,
    EvidenceSpan,
    WorkflowState,
)
from dd_context_engine.graph.neo4j_repo import Neo4jRelationshipRepository
from dd_context_engine.retrieval.postgres import PostgresRetrievalRepository
from dd_context_engine.storage.db import engine
from dd_context_engine.storage.postgres import (
    PostgresAssertionRepository,
    PostgresEvidenceRepository,
    PostgresWorkflowRepository,
)

relationship_repo: Neo4jRelationshipRepository | None = None

if settings.enable_graph:
    if not all(
        (
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
        )
    ):
        raise RuntimeError(
            "Graph is enabled but DD_NEO4J_URI, DD_NEO4J_USER and "
            "DD_NEO4J_PASSWORD are not all configured"
        )

    relationship_repo = Neo4jRelationshipRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    if relationship_repo is not None:
        await relationship_repo.close()

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)


evidence_repo = PostgresEvidenceRepository()
assertion_repo = PostgresAssertionRepository()
workflow_repo = PostgresWorkflowRepository()
retrieval_repo = PostgresRetrievalRepository()

context_service = ContextAssemblyService(
    workflow=workflow_repo,
    assertions=assertion_repo,
    evidence=evidence_repo,
    relationships=relationship_repo,
    retrieval=retrieval_repo,
    semantic=retrieval_repo,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    return {"status": "ready"}


@app.post("/v1/evidence", status_code=202)
async def ingest_evidence(
    envelope: EvidenceEnvelope,
) -> dict[str, object]:
    created = await evidence_repo.put_envelope(envelope)

    return {
        "source_id": str(envelope.source_id),
        "created": created,
    }


@app.post("/v1/evidence/spans", status_code=202)
async def add_evidence_span(
    span: EvidenceSpan,
) -> dict[str, object]:
    created = await evidence_repo.put_span(span)

    return {
        "span_id": str(span.span_id),
        "created": created,
    }


@app.post("/v1/evidence/embeddings", status_code=202)
async def add_evidence_embedding(
    embedding: EvidenceEmbedding,
) -> dict[str, object]:
    created = await retrieval_repo.put_embedding(embedding)

    return {
        "embedding_id": str(embedding.embedding_id),
        "created": created,
    }


@app.post("/v1/assertions", status_code=202)
async def add_assertion(
    assertion: CommercialAssertion,
) -> dict[str, object]:
    created = await assertion_repo.put(assertion)

    return {
        "assertion_id": str(assertion.assertion_id),
        "created": created,
    }


@app.put(
    "/v1/workflow/{tenant_id}/{case_id}",
    response_model=WorkflowState,
)
async def put_workflow(
    tenant_id: str,
    case_id: str,
    state: WorkflowState,
) -> WorkflowState:
    if state.tenant_id != tenant_id:
        raise HTTPException(
            status_code=400,
            detail="tenant_id does not match workflow path",
        )

    if state.case_id != case_id:
        raise HTTPException(
            status_code=400,
            detail="case_id does not match workflow path",
        )

    await workflow_repo.put(state)
    return state


@app.get(
    "/v1/workflow/{tenant_id}/{case_id}",
    response_model=WorkflowState,
)
async def get_workflow(
    tenant_id: str,
    case_id: str,
) -> WorkflowState:
    state = await workflow_repo.get(
        tenant_id=tenant_id,
        case_id=case_id,
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="workflow state not found",
        )

    return state


@app.post(
    "/v1/context/compile",
    response_model=ContextBundle,
)
async def compile_context(
    request: ContextRequest,
) -> ContextBundle:
    return await context_service.build(request)


@app.get("/version")
async def version() -> dict[str, str]:
    return {
        "version": app.version,
        "checked_at": datetime.now(UTC).isoformat(),
    }
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete

from dd_context_engine.api.app import app
from dd_context_engine.storage.db import engine, session_factory
from dd_context_engine.storage.models import (
    AssertionRecord,
    EvidenceEmbeddingRecord,
    EvidenceSpanRecord,
    SourceRecord,
    WorkflowStateRecord,
)

EMBEDDING_MODEL = "validation-embedding"
EMBEDDING_VERSION = "v1"


def source_payload(
    *,
    source_id,
    tenant_id,
    source_type,
    source_system,
    source_version,
    text,
    observed_at,
):
    return {
        "source_id": str(source_id),
        "tenant_id": tenant_id,
        "source_type": source_type,
        "source_system": source_system,
        "source_version": source_version,
        "content_type": "text/plain",
        "content_uri": f"validation://{source_id}",
        "observed_at": observed_at.isoformat(),
        "ingested_at": observed_at.isoformat(),
        "checksum_sha256": ("a" * 64),
        "metadata": {},
        "permissions": {"visibility": "tenant"},
    }


def span_payload(*, span_id, tenant_id, source_id, text):
    return {
        "span_id": str(span_id),
        "tenant_id": tenant_id,
        "source_id": str(source_id),
        "start_offset": 0,
        "end_offset": len(text),
        "text": text,
    }


def assertion_payload(
    *,
    assertion_id,
    tenant_id,
    entity_id,
    value,
    recorded_at,
    valid_from,
    status,
    source_id,
    evidence_span_id,
    supersedes_assertion_id=None,
):
    payload = {
        "assertion_id": str(assertion_id),
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "attribute": "funding_rate",
        "value": value,
        "recorded_at": recorded_at.isoformat(),
        "status": status,
        "source_id": str(source_id),
        "evidence_span_id": str(evidence_span_id),
        "extractor_name": "realworld-validation",
        "extractor_version": "1",
    }

    if valid_from is not None:
        payload["valid_from"] = valid_from.isoformat()

    if supersedes_assertion_id is not None:
        payload["supersedes_assertion_id"] = str(supersedes_assertion_id)

    return payload


def embedding_payload(*, embedding_id, tenant_id, span_id, vector):
    return {
        "embedding_id": str(embedding_id),
        "tenant_id": tenant_id,
        "span_id": str(span_id),
        "model_name": EMBEDDING_MODEL,
        "model_version": EMBEDDING_VERSION,
        "dimensions": len(vector),
        "embedding": vector,
    }


async def post_expect_created(client, path, payload):
    response = await client.post(path, json=payload)
    if response.status_code != 202:
        raise AssertionError(
            f"{path} returned {response.status_code}: {response.text}"
        )
    return response.json()


async def cleanup(tenant_ids: list[str]) -> None:
    async with session_factory() as session:
        await session.execute(
            delete(WorkflowStateRecord).where(
                WorkflowStateRecord.tenant_id.in_(tenant_ids)
            )
        )
        await session.execute(
            delete(AssertionRecord).where(
                AssertionRecord.tenant_id.in_(tenant_ids)
            )
        )
        await session.execute(
            delete(EvidenceEmbeddingRecord).where(
                EvidenceEmbeddingRecord.tenant_id.in_(tenant_ids)
            )
        )
        await session.execute(
            delete(EvidenceSpanRecord).where(
                EvidenceSpanRecord.tenant_id.in_(tenant_ids)
            )
        )
        await session.execute(
            delete(SourceRecord).where(
                SourceRecord.tenant_id.in_(tenant_ids)
            )
        )
        await session.commit()


async def main() -> None:
    tenant_id = f"validation-{uuid4()}"
    isolated_tenant_id = f"isolated-{uuid4()}"
    case_id = f"case-{uuid4()}"

    jan_1 = datetime(2026, 1, 1, tzinfo=UTC)
    apr_1 = datetime(2026, 4, 1, tzinfo=UTC)
    apr_5 = datetime(2026, 4, 5, tzinfo=UTC)
    apr_15 = datetime(2026, 4, 15, tzinfo=UTC)
    feb_1 = datetime(2026, 2, 1, tzinfo=UTC)
    may_1 = datetime(2026, 5, 1, tzinfo=UTC)

    contract_source = uuid4()
    amendment_source = uuid4()
    negotiation_source = uuid4()
    draft_source = uuid4()
    invoice_source = uuid4()
    isolated_source = uuid4()

    contract_span = uuid4()
    amendment_span = uuid4()
    negotiation_span = uuid4()
    draft_span = uuid4()
    invoice_span = uuid4()
    isolated_span = uuid4()

    contract_assertion = uuid4()
    amendment_assertion = uuid4()
    draft_assertion = uuid4()

    checks: list[dict[str, object]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "passed": condition,
                "detail": detail,
            }
        )
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    base_url = os.getenv("DD_BASE_URL")

    if base_url:
        client = httpx.AsyncClient(base_url=base_url)
    else:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    try:
        health = await client.get("/healthz")
        check(
            "health",
            health.status_code == 200,
            str(health.json()),
        )

        ready = await client.get("/readyz")
        check(
            "database readiness",
            ready.status_code == 200
            and ready.json().get("status") == "ready",
            ready.text,
        )

        sources = [
            (
                contract_source,
                "pdf",
                "contract-system",
                "1",
                "Master service agreement: funding rate is 10% effective 2026-01-01.",
                jan_1,
                contract_span,
                [0.80, 0.20],
            ),
            (
                amendment_source,
                "pdf",
                "contract-system",
                "2",
                "April amendment changes funding rate to 12% effective 2026-04-01.",
                apr_1,
                amendment_span,
                [1.00, 0.00],
            ),
            (
                negotiation_source,
                "email",
                "mail-system",
                "1",
                "Negotiation email confirms the final funding rate is 12% from April 1.",
                apr_5,
                negotiation_span,
                [0.95, 0.05],
            ),
            (
                draft_source,
                "email",
                "mail-system",
                "1",
                "Earlier negotiation draft proposed an 11% funding rate.",
                apr_5,
                draft_span,
                [0.85, 0.15],
            ),
            (
                invoice_source,
                "invoice",
                "erp",
                "1",
                "Invoice INV-1042 is due monthly and contains no funding-rate change.",
                apr_15,
                invoice_span,
                [0.00, 1.00],
            ),
            (
                isolated_source,
                "email",
                "other-tenant-system",
                "1",
                "Other tenant vendor funding rate is 99%.",
                apr_15,
                isolated_span,
                [1.00, 0.00],
            ),
        ]

        for (
            source_id,
            source_type,
            source_system,
            source_version,
            text,
            observed_at,
            span_id,
            vector,
        ) in sources:
            current_tenant = (
                isolated_tenant_id
                if source_id == isolated_source
                else tenant_id
            )

            source = await post_expect_created(
                client,
                "/v1/evidence",
                source_payload(
                    source_id=source_id,
                    tenant_id=current_tenant,
                    source_type=source_type,
                    source_system=source_system,
                    source_version=source_version,
                    text=text,
                    observed_at=observed_at,
                ),
            )

            span = await post_expect_created(
                client,
                "/v1/evidence/spans",
                span_payload(
                    span_id=span_id,
                    tenant_id=current_tenant,
                    source_id=source_id,
                    text=text,
                ),
            )

            embedding = await post_expect_created(
                client,
                "/v1/evidence/embeddings",
                embedding_payload(
                    embedding_id=uuid4(),
                    tenant_id=current_tenant,
                    span_id=span_id,
                    vector=vector,
                ),
            )

            check("source inserted", source["created"] is True, str(source))
            check("span inserted", span["created"] is True, str(span))
            check(
                "embedding inserted",
                embedding["created"] is True,
                str(embedding),
            )

        workflow = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "stage": "analysis",
            "goal": "Determine the current funding terms",
            "completed_steps": ["ingestion", "extraction"],
            "pending_steps": ["context_review"],
            "unresolved_conflicts": [],
            "tool_results": [],
            "approval_state": None,
            "checkpoint": "assertions_loaded",
            "retry_count": 0,
            "model_version": "validation-model",
            "prompt_version": "validation-prompt-v1",
            "updated_at": may_1.isoformat(),
        }

        workflow_write = await client.put(
            f"/v1/workflow/{tenant_id}/{case_id}",
            json=workflow,
        )

        check(
            "workflow write",
            workflow_write.status_code == 200,
            workflow_write.text,
        )

        workflow_read = await client.get(
            f"/v1/workflow/{tenant_id}/{case_id}",
        )

        check(
            "workflow persistence",
            workflow_read.status_code == 200
            and workflow_read.json()["checkpoint"] == "assertions_loaded",
            workflow_read.text,
        )

        assert_a = await post_expect_created(
            client,
            "/v1/assertions",
            assertion_payload(
                assertion_id=contract_assertion,
                tenant_id=tenant_id,
                entity_id="vendor-acme",
                value=0.10,
                recorded_at=jan_1,
                valid_from=jan_1,
                status="active",
                source_id=contract_source,
                evidence_span_id=contract_span,
            ),
        )

        assert_b = await post_expect_created(
            client,
            "/v1/assertions",
            assertion_payload(
                assertion_id=amendment_assertion,
                tenant_id=tenant_id,
                entity_id="vendor-acme",
                value=0.12,
                recorded_at=apr_15,
                valid_from=apr_1,
                status="active",
                source_id=amendment_source,
                evidence_span_id=amendment_span,
                supersedes_assertion_id=contract_assertion,
            ),
        )

        await post_expect_created(
            client,
            "/v1/assertions",
            assertion_payload(
                assertion_id=draft_assertion,
                tenant_id=tenant_id,
                entity_id="vendor-acme",
                value=0.11,
                recorded_at=apr_5,
                valid_from=apr_1,
                status="candidate",
                source_id=draft_source,
                evidence_span_id=draft_span,
            ),
        )

        check(
            "assertion creation",
            assert_a["created"] is True and assert_b["created"] is True,
            f"{assert_a} / {assert_b}",
        )

        duplicate_assertion = await client.post(
            "/v1/assertions",
            json=assertion_payload(
                assertion_id=amendment_assertion,
                tenant_id=tenant_id,
                entity_id="vendor-acme",
                value=0.12,
                recorded_at=apr_15,
                valid_from=apr_1,
                status="active",
                source_id=amendment_source,
                evidence_span_id=amendment_span,
                supersedes_assertion_id=contract_assertion,
            ),
        )

        check(
            "assertion idempotency",
            duplicate_assertion.status_code == 202
            and duplicate_assertion.json()["created"] is False,
            duplicate_assertion.text,
        )

        current_context = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "task": "What is the final funding rate after the amendment?",
            "entity_id": "vendor-acme",
            "at_time": may_1.isoformat(),
            "query_embedding": [1.0, 0.0],
            "embedding_model": EMBEDDING_MODEL,
            "embedding_version": EMBEDDING_VERSION,
            "max_assertions": 10,
            "max_evidence_items": 3,
        }

        started = time.perf_counter()
        current_response = await client.post(
            "/v1/context/compile",
            json=current_context,
        )
        current_latency_ms = (time.perf_counter() - started) * 1000

        check(
            "current context compiles",
            current_response.status_code == 200,
            current_response.text,
        )

        current = current_response.json()

        current_values = {
            assertion["value"]
            for assertion in current["assertions"]
        }

        check(
            "current temporal correctness",
            0.12 in current_values and 0.10 not in current_values,
            str(current_values),
        )

        check(
            "provenance survives context assembly",
            any(
                assertion["evidence_span_id"] == str(amendment_span)
                for assertion in current["assertions"]
            ),
            current["assertions"],
        )

        check(
            "conflict detection",
            len(current["conflicts"]) == 1,
            str(current["conflicts"]),
        )

        check(
            "context is bounded",
            current["bounded"] is True
            and len(current["evidence"]) <= 3,
            str(len(current["evidence"])),
        )

        historical_response = await client.post(
            "/v1/context/compile",
            json={
                **current_context,
                "task": "What funding rate was valid in February?",
                "at_time": feb_1.isoformat(),
                "max_evidence_items": 3,
            },
        )

        check(
            "historical context compiles",
            historical_response.status_code == 200,
            historical_response.text,
        )

        historical = historical_response.json()
        historical_values = {
            assertion["value"]
            for assertion in historical["assertions"]
        }

        check(
            "historical temporal correctness",
            historical_values == {0.10},
            str(historical_values),
        )

        retrieval_response = await client.post(
            "/v1/context/compile",
            json={
                "tenant_id": tenant_id,
                "case_id": case_id,
                "task": "Which evidence confirms the amended rate?",
                "query_embedding": [1.0, 0.0],
                "embedding_model": EMBEDDING_MODEL,
                "embedding_version": EMBEDDING_VERSION,
                "max_assertions": 5,
                "max_evidence_items": 3,
            },
        )

        retrieval_body = retrieval_response.json()
        retrieval_text = " ".join(
            item["text"]
            for item in retrieval_body["evidence"]
        )

        check(
            "hybrid retrieval finds relevant evidence",
            "12%" in retrieval_text,
            retrieval_text,
        )

        check(
            "tenant isolation",
            "99%" not in retrieval_text,
            retrieval_text,
        )

        duplicate_span = await client.post(
            "/v1/evidence/spans",
            json=span_payload(
                span_id=amendment_span,
                tenant_id=tenant_id,
                source_id=amendment_source,
                text=(
                    "April amendment changes funding rate "
                    "to 12% effective 2026-04-01."
                ),
            ),
        )

        check(
            "span idempotency",
            duplicate_span.status_code == 202
            and duplicate_span.json()["created"] is False,
            duplicate_span.text,
        )

        timings = [current_latency_ms]

        for _ in range(19):
            started = time.perf_counter()

            response = await client.post(
                "/v1/context/compile",
                json=current_context,
            )

            timings.append(
                (time.perf_counter() - started) * 1000
            )

            if response.status_code != 200:
                raise AssertionError(response.text)

        sorted_timings = sorted(timings)

        p50 = statistics.median(sorted_timings)
        p95 = sorted_timings[
            min(len(sorted_timings) - 1, int(len(sorted_timings) * 0.95))
        ]

        report = {
            "status": "PASS",
            "generated_at": datetime.now(UTC).isoformat(),
            "tenant": tenant_id,
            "scenario": {
                "sources": 6,
                "spans": 6,
                "assertions": 3,
                "embeddings": 6,
            },
            "checks": checks,
            "latency_ms": {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "samples": len(timings),
            },
        }

        output_dir = Path("artifacts")
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / "realworld_validation.json"
        output_file.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(report, indent=2))

    finally:
        await client.aclose()
        await cleanup([tenant_id, isolated_tenant_id])
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
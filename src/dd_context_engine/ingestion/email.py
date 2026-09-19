from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from uuid import UUID, uuid5

from dd_context_engine.domain.ports import EvidenceRepository
from dd_context_engine.domain.schemas import (
    EvidenceEnvelope,
    EvidenceSpan,
    SourceType,
)

EMAIL_SOURCE_NAMESPACE = UUID("8d4e7a72-3d5e-4d7e-9f5e-6a4d8c2b1e90")


@dataclass(frozen=True, slots=True)
class EmailThreadKey:
    message_id: str
    parent_id: str | None
    references: tuple[str, ...]


def reconstruct_thread_key(headers: dict[str, str]) -> EmailThreadKey:
    normalized = {key.lower(): value for key, value in headers.items()}

    message_id = normalized.get("message-id", "").strip()
    if not message_id:
        raise ValueError("Message-ID is required for deterministic email threading")

    parent_id = normalized.get("in-reply-to", "").strip() or None
    references = tuple(
        value
        for value in normalized.get("references", "").split()
        if value
    )

    return EmailThreadKey(
        message_id=message_id,
        parent_id=parent_id,
        references=references,
    )


def _extract_body(message) -> str:
    if message.is_multipart():
        plain_parts: list[str] = []

        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() != "text/plain":
                continue

            content = part.get_content()
            if isinstance(content, str) and content.strip():
                plain_parts.append(content.strip())

        if plain_parts:
            return "\n\n".join(plain_parts)

    content = message.get_content()
    if isinstance(content, str) and content.strip():
        return content.strip()

    raise ValueError("Email contains no readable text/plain body")


class EmailIngestionService:
    def __init__(self, evidence: EvidenceRepository) -> None:
        self._evidence = evidence

    async def ingest(
        self,
        *,
        tenant_id: str,
        raw_email: bytes,
        observed_at: datetime | None = None,
    ) -> EvidenceEnvelope:
        message = BytesParser(policy=policy.default).parsebytes(raw_email)

        headers = {key: str(value) for key, value in message.items()}
        thread = reconstruct_thread_key(headers)

        source_id = uuid5(
            EMAIL_SOURCE_NAMESPACE,
            f"{tenant_id}:{thread.message_id}",
        )

        body = _extract_body(message)

        now = datetime.now(UTC)
        observed = observed_at or now
        checksum = hashlib.sha256(raw_email).hexdigest()

        envelope = EvidenceEnvelope(
            source_id=source_id,
            tenant_id=tenant_id,
            source_type=SourceType.EMAIL,
            source_system="email",
            source_version=thread.message_id,
            content_type=message.get_content_type(),
            content_uri=f"email://{thread.message_id}",
            observed_at=observed,
            ingested_at=now,
            checksum_sha256=checksum,
            metadata={
                "message_id": thread.message_id,
                "parent_id": thread.parent_id,
                "references": list(thread.references),
                "subject": message.get("Subject"),
                "from": message.get("From"),
                "to": message.get("To"),
                "cc": message.get("Cc"),
            },
            permissions={"visibility": "tenant"},
        )

        await self._evidence.put_envelope(envelope)

        span_id = uuid5(source_id, "body")

        span = EvidenceSpan(
            span_id=span_id,
            tenant_id=tenant_id,
            source_id=source_id,
            start_offset=0,
            end_offset=len(body),
            text=body,
        )

        await self._evidence.put_span(span)

        return envelope
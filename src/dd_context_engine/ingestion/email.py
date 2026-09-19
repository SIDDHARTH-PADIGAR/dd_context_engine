from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailThreadKey:
    message_id: str
    parent_id: str | None
    references: tuple[str, ...]


def reconstruct_thread_key(headers: dict[str, str]) -> EmailThreadKey:
    message_id = headers.get("Message-ID", "").strip()
    if not message_id:
        raise ValueError("Message-ID is required for deterministic email threading")
    parent_id = headers.get("In-Reply-To", "").strip() or None
    references = tuple(x for x in headers.get("References", "").split() if x)
    return EmailThreadKey(message_id, parent_id, references)

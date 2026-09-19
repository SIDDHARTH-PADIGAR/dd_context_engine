# DD Context Engine

Scalable foundation for the **memory, evidence and working-context side** of a long-running enterprise AI agent.

This is not a chatbot or prompt demo. The code uses durable Postgres state, versioned assertions, source provenance, tenant-aware records, idempotent inserts, outbox-ready events, optional graph projection and container/Kubernetes deployment structure.

It is not claimed to be Discover Dollar's internal implementation or immediately deployable into their private production environment. Their private interfaces and operational requirements are not public.

See:
- `ARCHITECTURE.md`
- `RESEARCH_AUDIT.md`
- `alembic/versions/0001_initial.py`

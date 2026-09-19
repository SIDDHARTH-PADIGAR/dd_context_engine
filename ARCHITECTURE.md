# Locked Design: Autonomous Agent Context and Memory Foundation

This repository implements the technical context/memory foundation only. It does not encode Discover Dollar's proprietary financial audit rules.

## Architecture

```text
CLIENT DATA
ERP / AP / invoices / POs / email / contracts / amendments / spreadsheets
                         |
                         v
                 INGESTION GATEWAY
          tenant + source + version + checksum
                         |
                         v
             IMMUTABLE EVIDENCE METADATA
                  (object-storage URI)
                         |
                         v
              EXTRACTION / RESOLUTION
        replaceable NLP/ML model integrations
                         |
                         v
        CANONICAL VERSIONED ASSERTIONS
       value + scope + valid time + provenance
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
      SQL facts      Search index   Graph projection
      + workflow     lexical/vector  OPTIONAL / derived
          |              |               |
          +--------------+---------------+
                         |
                         v
             CONTEXT ASSEMBLY SERVICE
          task state + facts + evidence
          + relationships + conflicts
                         |
                         v
              BOUNDED WORKING CONTEXT
                         |
                         v
                 TYPED AGENT TOOLS
                         |
                         v
                    AGENT MODEL
                         |
                         v
               DURABLE STATE UPDATES

Cross-cutting: tenant isolation, authentication, idempotency, audit,
model/version tracking, retries, observability, cost controls.
```

## Non-negotiable rules

- Raw evidence is preserved outside the model.
- Durable business state is structured and versioned.
- Workflow state is separate from business state.
- The model context is temporary working state.
- The graph is optional and derived; it is never authoritative.
- Domain-specific financial truth rules belong outside this subsystem.
- Duplicate input is safe because writes use tenant-scoped identifiers.
- Model/extractor versions are persisted with assertions.
- Tenant boundaries are carried through every durable object.
- A failed worker can restart from durable state.

## Production boundary

This code is deployable and production-oriented, but it is not claimed to be ready for direct Discover Dollar deployment because their private APIs, infrastructure, security controls, data contracts, model stack and operational requirements are not public.

## Current scope

Included:
- durable Postgres state
- immutable source metadata
- evidence spans
- versioned assertions
- workflow state
- outbox schema
- deterministic RFC-style email thread key extraction
- bounded context assembly
- optional Neo4j relationship adapter
- container image
- Kubernetes deployment skeleton
- migration
- unit tests

Intentionally deferred:
- production LLM provider selection
- production search/vector backend
- graph activation decision
- autonomous financial actions
- financial authority rules
- external system connectors

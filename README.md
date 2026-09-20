# DD Context Engine

## TL;DR

I built this as a context and memory foundation for a long-running enterprise agent.

The problem I was solving is simple to describe but difficult to implement well: the information an agent needs is not sitting in one document or one prompt. It is spread across ERP records, invoices, purchase orders, contracts, amendments, emails and spreadsheets, and some of that information changes over time.

I did **not** have access to Discover Dollar's internal memory system, private APIs or production data, so I did not try to recreate something I could not see.

Instead, I built the part I could defend from the available evidence:

**Raw evidence → versioned state → retrieval → context assembly → bounded working context → agent → durable state update**

The core decision is:

> **I keep durable truth outside the model and make the model consume a small, task-specific working set.**

---

## The problem I started from

A question like:

> "What funding rate applies to this vendor?"

may depend on a contract, an amendment, a negotiation email, the extracted commercial term, the evidence supporting it, and the current workflow state.

That creates four different kinds of state:

| State               | What I keep there                                    |
| ------------------- | ---------------------------------------------------- |
| **Evidence**        | Source metadata and exact evidence spans             |
| **Business state**  | Canonical claims, validity, provenance, supersession |
| **Workflow state**  | Case progress, retries, checkpoints, approvals       |
| **Working context** | Only the information needed for the current task     |

I kept these separate deliberately. A workflow checkpoint should not become a business fact. A model prompt should not become permanent memory. A graph should not silently become financial truth.

---

## How I got to this design

I used the research to answer specific engineering questions rather than copy architectures from papers.

### MemGPT — where should long-term state live?

[MemGPT](https://arxiv.org/abs/2310.08560) gave me the starting point: the model's immediate context should not be treated as the whole memory system.

That led me to move durable state into persistence and make context something assembled for a task.

### Generative Agents — how should relevant memory be brought back?

[Generative Agents](https://arxiv.org/abs/2304.03442) reinforced the retrieval side of the design: do not replay an entire history every time the agent reasons.

I applied that to enterprise data through:

**PostgreSQL lexical search + pgvector semantic search → hybrid RRF ranking → context compiler**

Retrieval happens before context compilation, so the model receives a bounded working set instead of an ever-growing history.

### CoALA — what belongs inside the agent and what does not?

[CoALA](https://arxiv.org/abs/2309.02427) helped me separate memory, actions and reasoning.

That became:

| Concern                   | System boundary        |
| ------------------------- | ---------------------- |
| Memory / facts / evidence | Persistence            |
| Workflow                  | Durable workflow state |
| Retrieval                 | Retrieval layer        |
| Reasoning                 | Model                  |
| Actions                   | Typed agent tools      |

That separation lets the underlying state model stay independent of the model or retrieval implementation.

### Mem0 — should memory and graph be treated as magic?

[Mem0](https://arxiv.org/abs/2504.19413) made me more conservative.

The results support selective persistent memory, but they do not justify making a graph authoritative for every question.

So I made the graph **optional and derived**:

**PostgreSQL + evidence → authoritative state**

**Neo4j → relationship retrieval / traversal**

The papers support the direction of the design. They do not prove that the same results will transfer directly to Discover Dollar's workload.

---

## Why I version assertions instead of overwriting facts

This was one of the first places where a basic implementation would break down.

Suppose I extract:

| Date               | Funding rate |
| ------------------ | -----------: |
| Jan 2026           |          10% |
| Apr 2026 amendment |          12% |

I do not turn `10%` into `12%`.

I keep both assertions and record:

`valid_from` · `valid_to` · `recorded_at` · `status` · `source_id` · `evidence_span_id` · `extractor_version` · `supersedes_assertion_id`

That lets the system distinguish:

**"What is the current rate?"**

from

**"What rate was valid in February?"**

from

**"Which evidence caused the change?"**

---

## Why provenance is part of the data model

I did not want the final answer to depend on the model remembering where something came from.

The lineage is explicit:

**agent output → assertion → evidence span → source record → original document**

An extracted fact therefore carries a path back to evidence, along with the extractor/model version used to produce it.

---

## What makes this more than a toy prototype

I designed the persistence and boundaries around the failure modes I would expect once the data and number of cases grow.

```mermaid
flowchart TD
    A["ERP / AP / Invoices / POs / Contracts / Amendments / Emails / Spreadsheets"]
    B["Ingestion"]
    C["Immutable Evidence"]
    D["Versioned Assertions"]

    E["PostgreSQL Facts"]
    F["Workflow State"]
    G["Lexical + Vector Retrieval"]
    H["Optional Neo4j Projection"]

    I["Context Compiler"]
    J["Bounded Working Context"]
    K["Typed Agent Tools"]
    L["Agent Model"]

    M["Durable State Update"]

    A --> B --> C --> D
    D --> E
    D --> G
    D --> H
    F --> I
    E --> I
    G --> I
    H --> I
    I --> J --> K --> L --> M
    M --> F
    M --> E
```

The architecture is backed by concrete implementation choices:

| Problem                                 | Decision                                |
| --------------------------------------- | --------------------------------------- |
| Duplicate ingestion                     | Stable, tenant-scoped identifiers       |
| Changing business terms                 | Versioned assertions + supersession     |
| Historical queries                      | Temporal validity instead of overwrites |
| Untraceable answers                     | Evidence spans + provenance             |
| Growing context                         | Retrieval before context compilation    |
| Retrieval lock-in                       | Repository interfaces                   |
| Graph becoming a second source of truth | Graph kept derived and optional         |
| Failed long-running work                | Durable workflow checkpoints            |
| Schema drift                            | Alembic migrations                      |
| Cross-feature regressions               | Integration tests                       |

I have not claimed a benchmark at Discover Dollar's production scale because I do not have their data or workload.

What I have built is a persistence and retrieval path that is designed around explicit boundaries, transactions, tenant isolation and bounded context rather than putting the entire enterprise history into the model.

---

## Validation

After the implementation was green, I ran it as a system rather than relying only on unit tests.

The validation scenario used synthetic enterprise data representing a contract, an amendment, negotiation emails, an invoice and a second tenant.

It exercised:

**ingestion → evidence → assertions → retrieval → context assembly → workflow state**

The scenario used:

* **6 sources**
* **6 evidence spans**
* **3 assertions**
* **6 embeddings**

It verified:

* current and historical terms
* assertion supersession
* provenance back to the supporting evidence
* conflict detection
* hybrid retrieval
* tenant isolation
* duplicate-write idempotency
* durable workflow state
* bounded context

The measured local result was:

**20 automated tests passing · validation scenario PASS · 15.20 ms p50 · 32.27 ms p95**

The latency numbers are from this synthetic validation workload, not a production SLA or a claim about Discover Dollar's eventual workload.

---

## What I actually built

### Evidence

* Source metadata
* Evidence spans
* Deterministic email threading
* Provenance

### Business state

* Canonical assertions
* Temporal validity
* Supersession
* Extractor/model version tracking

### Workflow

* Durable case state
* Checkpoints
* Retries
* Pending/completed steps

### Retrieval

* PostgreSQL lexical search
* pgvector semantic search
* Hybrid RRF retrieval

### Context

* Task-aware retrieval
* Conflict handling
* Bounded context compilation

### Graph

* Optional Neo4j relationship traversal
* Tenant-safe, depth-bounded traversal
* Derived rather than authoritative state

### Runtime

* Workflow GET/PUT
* Evidence endpoints
* Embedding endpoint
* Context compilation API

### Engineering

* Alembic migrations
* PostgreSQL integration tests
* API integration tests
* Real-world validation scenario
* Repository interfaces
* Ruff linting

---

## The boundary I am defending

This repository is **not** Discover Dollar's private implementation, and it is not a financial audit engine.

It is the part of the system I can justify from the available problem definition:

**Enterprise evidence → durable, versioned state → retrieval → controlled context → agent reasoning**

That is the design I chose because it gives an agent persistent memory without making the model responsible for persistence, provenance, temporal truth, workflow recovery or the entire enterprise history.

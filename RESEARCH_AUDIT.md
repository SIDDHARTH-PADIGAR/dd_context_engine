# Research audit boundary

The attached research record was checked against the underlying public sources before this repository was created.

Discover Dollar's public material establishes the mixed-data problem: ERP/structured records together with contracts, amendments, negotiation emails and spreadsheets, with temporal terms and recurring matching. It does not disclose Discover Dollar's internal memory/context implementation.

MemGPT supports externalized context/state. CoALA separates memory, actions and decision-making. Generative Agents supports retrieval/reflection patterns in a simulated environment. Mem0 reports substantial efficiency gains for selective memory and a small graph-memory gain, with graph gains varying by question type. Those studies do not prove the graph is best for enterprise financial data.

Therefore:

- structured durable state is a design decision for this workload;
- context assembly is our architecture term, not a claim that it is a standard named component;
- graph retrieval remains a benchmarked hypothesis;
- exact scale behavior must be measured against representative workloads;
- financial-domain rules remain outside this subsystem.

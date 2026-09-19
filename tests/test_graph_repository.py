import pytest

from dd_context_engine.graph.neo4j_repo import Neo4jRelationshipRepository


class FakeResult:
    def __init__(self, records):
        self.records = records

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for record in self.records:
            yield record


class FakeSession:
    def __init__(self):
        self.query = None
        self.parameters = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run(self, query, **parameters):
        self.query = query
        self.parameters = parameters

        return FakeResult(
            [
                {
                    "path": [
                        {
                            "entity_id": "vendor-1",
                            "tenant_id": "tenant-a",
                        },
                        {
                            "entity_id": "contract-1",
                            "tenant_id": "tenant-a",
                        },
                    ]
                }
            ]
        )


class FakeDriver:
    def __init__(self):
        self.session_instance = FakeSession()

    def session(self):
        return self.session_instance

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_graph_repository_enforces_tenant_and_limit():
    repository = object.__new__(Neo4jRelationshipRepository)
    repository._driver = FakeDriver()

    results = await repository.related(
        tenant_id="tenant-a",
        entity_ids=["vendor-1"],
        limit=8,
    )

    assert len(results) == 1

    session = repository._driver.session_instance

    assert session.parameters == {
        "tenant_id": "tenant-a",
        "entity_ids": ["vendor-1"],
        "limit": 8,
    }

    assert "all(" in session.query
    assert "node.tenant_id = $tenant_id" in session.query
    assert "LIMIT $limit" in session.query
    assert "DISTINCT" in session.query


@pytest.mark.asyncio
async def test_graph_repository_returns_empty_for_no_entities():
    repository = object.__new__(Neo4jRelationshipRepository)

    fake_driver = FakeDriver()
    repository._driver = fake_driver

    results = await repository.related(
        tenant_id="tenant-a",
        entity_ids=[],
        limit=8,
    )

    assert results == []


@pytest.mark.asyncio
async def test_graph_repository_rejects_invalid_limit():
    repository = object.__new__(Neo4jRelationshipRepository)
    repository._driver = FakeDriver()

    with pytest.raises(ValueError, match="limit must be >= 1"):
        await repository.related(
            tenant_id="tenant-a",
            entity_ids=["vendor-1"],
            limit=0,
        )
from __future__ import annotations

from neo4j import AsyncGraphDatabase


class Neo4jRelationshipRepository:
    """Optional relationship projection; the graph is never the authority."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        await self._driver.close()

    async def related(self, tenant_id: str, entity_ids: list[str], limit: int) -> list[dict]:
        if not entity_ids:
            return []
        query = """
        MATCH (e:Entity {tenant_id: $tenant_id})
        WHERE e.entity_id IN $entity_ids
        MATCH p=(e)-[*1..3]-(n)
        RETURN [x IN nodes(p) | properties(x)] AS path
        LIMIT $limit
        """
        async with self._driver.session() as session:
            result = await session.run(query, tenant_id=tenant_id, entity_ids=entity_ids, limit=limit)
            return [record["path"] async for record in result]

from __future__ import annotations

from neo4j import AsyncGraphDatabase


class Neo4jRelationshipRepository:
    """Optional relationship projection; the graph is never the authority."""

    MAX_TRAVERSAL_DEPTH = 3

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
        )

    async def close(self) -> None:
        await self._driver.close()

    async def related(
        self,
        tenant_id: str,
        entity_ids: list[str],
        limit: int,
    ) -> list[dict]:
        if not entity_ids:
            return []

        if limit < 1:
            raise ValueError("limit must be >= 1")

        query = """
        MATCH (e:Entity {tenant_id: $tenant_id})
        WHERE e.entity_id IN $entity_ids
        MATCH p=(e)-[*1..3]-(n)
        WHERE all(
            node IN nodes(p)
            WHERE node.tenant_id = $tenant_id
        )
        RETURN DISTINCT
            [x IN nodes(p) | properties(x)] AS path
        ORDER BY
            length(p),
            coalesce(n.entity_id, "")
        LIMIT $limit
        """

        async with self._driver.session() as session:
            result = await session.run(
                query,
                tenant_id=tenant_id,
                entity_ids=entity_ids,
                limit=limit,
            )

            paths: list[dict] = []

            async for record in result:
                paths.append({"path": record["path"]})

            return paths
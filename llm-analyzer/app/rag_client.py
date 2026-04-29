from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .rag_models import QdrantDistance, RagSearchFilters


@dataclass(frozen=True)
class RagPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True)
class RagScoredPoint:
    id: str
    score: float
    payload: dict[str, Any]


class RagVectorStore(Protocol):
    def ensure_collection(
        self, collection: str, vector_size: int, distance: QdrantDistance
    ) -> None:
        ...

    def upsert_points(self, collection: str, points: list[RagPoint]) -> None:
        ...

    def search(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: RagSearchFilters | None = None,
    ) -> list[RagScoredPoint]:
        ...


class QdrantRestClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds)

    def ensure_collection(
        self, collection: str, vector_size: int, distance: QdrantDistance
    ) -> None:
        response = self._client.get(f"{self.base_url}/collections/{collection}")
        if response.status_code == 404:
            create_response = self._client.put(
                f"{self.base_url}/collections/{collection}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": distance,
                    }
                },
            )
            create_response.raise_for_status()
            return

        response.raise_for_status()

    def upsert_points(self, collection: str, points: list[RagPoint]) -> None:
        if not points:
            return

        response = self._client.put(
            f"{self.base_url}/collections/{collection}/points",
            params={"wait": "true"},
            json={
                "points": [
                    {
                        "id": point.id,
                        "vector": point.vector,
                        "payload": point.payload,
                    }
                    for point in points
                ]
            },
        )
        response.raise_for_status()

    def search(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: RagSearchFilters | None = None,
    ) -> list[RagScoredPoint]:
        body: dict[str, Any] = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }
        qdrant_filter = _qdrant_filter(filters)
        if qdrant_filter:
            body["filter"] = qdrant_filter

        response = self._client.post(
            f"{self.base_url}/collections/{collection}/points/search",
            json=body,
        )
        response.raise_for_status()
        result = response.json().get("result", [])
        return [
            RagScoredPoint(
                id=str(point["id"]),
                score=max(float(point.get("score", 0)), 0),
                payload=point.get("payload") or {},
            )
            for point in result
        ]

    def close(self) -> None:
        self._client.close()


class InMemoryRagStore:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, RagPoint]] = {}
        self.collection_specs: dict[str, tuple[int, QdrantDistance]] = {}
        self.ensure_collection_calls: list[tuple[str, int, QdrantDistance]] = []
        self.upsert_calls: list[tuple[str, list[RagPoint]]] = []

    def ensure_collection(
        self, collection: str, vector_size: int, distance: QdrantDistance
    ) -> None:
        self.ensure_collection_calls.append((collection, vector_size, distance))
        existing_spec = self.collection_specs.get(collection)
        requested_spec = (vector_size, distance)
        if existing_spec is not None and existing_spec != requested_spec:
            raise ValueError(
                f"collection {collection!r} already has vector spec {existing_spec}"
            )

        self.collection_specs[collection] = requested_spec
        self.collections.setdefault(collection, {})

    def upsert_points(self, collection: str, points: list[RagPoint]) -> None:
        self.upsert_calls.append((collection, points))
        if collection not in self.collections:
            raise ValueError(f"collection {collection!r} does not exist")

        vector_size, _distance = self.collection_specs[collection]
        for point in points:
            if len(point.vector) != vector_size:
                raise ValueError(
                    f"point {point.id!r} vector length does not match collection"
                )
            self.collections[collection][point.id] = point

    def search(
        self,
        collection: str,
        vector: list[float],
        limit: int,
        filters: RagSearchFilters | None = None,
    ) -> list[RagScoredPoint]:
        points = self.collections.get(collection, {}).values()
        scored = [
            RagScoredPoint(
                id=point.id,
                score=max(_cosine_similarity(vector, point.vector), 0),
                payload=point.payload,
            )
            for point in points
            if _matches_filters(point.payload, filters)
        ]
        scored.sort(key=lambda point: point.score, reverse=True)
        return scored[:limit]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same length")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot_product / (left_norm * right_norm)


def _matches_filters(
    payload: dict[str, Any], filters: RagSearchFilters | None
) -> bool:
    if filters is None:
        return True

    if filters.source_ids and payload.get("source_id") not in filters.source_ids:
        return False
    if filters.source_types and payload.get("source_type") not in filters.source_types:
        return False
    if filters.versions and payload.get("version") not in filters.versions:
        return False
    return True


def _qdrant_filter(filters: RagSearchFilters | None) -> dict[str, Any] | None:
    if filters is None:
        return None

    must: list[dict[str, Any]] = []
    if filters.source_ids:
        must.append({"key": "source_id", "match": {"any": filters.source_ids}})
    if filters.source_types:
        must.append({"key": "source_type", "match": {"any": filters.source_types}})
    if filters.versions:
        must.append({"key": "version", "match": {"any": filters.versions}})

    if not must:
        return None
    return {"must": must}

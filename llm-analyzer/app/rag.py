from __future__ import annotations

import hashlib
import logging
import os
import re

from pydantic import ValidationError

from .rag_client import QdrantRestClient, RagScoredPoint, RagVectorStore
from .rag_models import RagChunk, RagSearchRequest, RagSearchResponse


logger = logging.getLogger("llm_analyzer.rag")


class HashingTextEmbedder:
    """Small deterministic query vectorizer for dev/test fallback paths."""

    def __init__(self, vector_size: int) -> None:
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        self.vector_size = vector_size

    def embed(self, text: str) -> list[float]:
        vector = [0.0 for _item in range(self.vector_size)]
        for token in _tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.vector_size
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        magnitude = sum(value * value for value in vector) ** 0.5
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


class RagSearchService:
    def __init__(
        self,
        store: RagVectorStore,
        collection: str,
        embedder: HashingTextEmbedder,
    ) -> None:
        self.store = store
        self.collection = collection
        self.embedder = embedder

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        if not request.normalized_query:
            return RagSearchResponse(chunks=[], chunk_ids=[])

        query_vector = request.query_vector or self.embedder.embed(request.normalized_query)
        scored_points = self.store.search(
            self.collection,
            query_vector,
            request.limit,
            request.filters,
        )
        chunks, chunk_ids = _chunks_from_points(scored_points)
        logger.info("rag_recovered_chunks chunk_ids=%s", ",".join(chunk_ids))
        return RagSearchResponse(chunks=chunks, chunk_ids=chunk_ids)


def build_default_rag_service() -> RagSearchService:
    vector_size = int(os.getenv("RAG_VECTOR_SIZE", "384"))
    timeout_seconds = float(
        os.getenv("QDRANT_TIMEOUT_SECONDS", os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "10"))
    )
    return RagSearchService(
        store=QdrantRestClient(
            base_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            timeout_seconds=timeout_seconds,
        ),
        collection=os.getenv("RAG_COLLECTION", "p4symtest-warnings"),
        embedder=HashingTextEmbedder(vector_size),
    )


def _chunks_from_points(points: list[RagScoredPoint]) -> tuple[list[RagChunk], list[str]]:
    chunks: list[RagChunk] = []
    chunk_ids: list[str] = []
    for point in points:
        try:
            chunk = _chunk_from_payload(point.payload, point.score)
        except ValidationError:
            logger.exception("rag_invalid_chunk_payload chunk_id=%s", point.id)
            continue

        chunks.append(chunk)
        chunk_ids.append(point.id)
    return chunks, chunk_ids


def _chunk_from_payload(payload: dict[str, object], score: float) -> RagChunk:
    chunk_fields = {
        "source_id",
        "title",
        "source_type",
        "citation",
        "version",
        "text",
    }
    data = {key: payload[key] for key in chunk_fields if key in payload}
    data["score"] = max(float(score), 0)
    return RagChunk.model_validate(data)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_.:-]+", text.lower())

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .rag_client import RagPoint, RagVectorStore
from .rag_models import RagIngestionResult, RagManifest, RagManifestChunk


STABLE_ID_NAMESPACE = uuid.UUID("e9ba3dc6-c60f-4b86-ae58-e9cb0f6a2a82")
RAG_CHUNK_PAYLOAD_FIELDS = {
    "source_id",
    "title",
    "source_type",
    "citation",
    "version",
    "text",
}


def load_rag_manifest(path: str | Path) -> RagManifest:
    with Path(path).open("r", encoding="utf-8") as file:
        return RagManifest.model_validate(json.load(file))


def stable_chunk_id(
    manifest: RagManifest, chunk: RagManifestChunk, chunk_index: int
) -> str:
    chunk_identity = chunk.chunk_key or str(chunk_index)
    stable_material = "\n".join(
        [
            manifest.manifest_id,
            manifest.manifest_version,
            chunk.source_id,
            chunk.version,
            chunk_identity,
            chunk.title,
            chunk.citation,
        ]
    )
    return str(uuid.uuid5(STABLE_ID_NAMESPACE, stable_material))


def build_rag_points(manifest: RagManifest) -> list[RagPoint]:
    return [
        RagPoint(
            id=stable_chunk_id(manifest, chunk, index),
            vector=chunk.embedding,
            payload=build_payload(manifest, chunk, index),
        )
        for index, chunk in enumerate(manifest.chunks)
    ]


def build_payload(
    manifest: RagManifest, chunk: RagManifestChunk, chunk_index: int
) -> dict[str, Any]:
    payload = chunk.as_rag_chunk().model_dump(exclude_none=True)
    payload.update(
        {
            "chunk_id": stable_chunk_id(manifest, chunk, chunk_index),
            "chunk_key": chunk.chunk_key,
            "manifest_id": manifest.manifest_id,
            "manifest_version": manifest.manifest_version,
            "metadata": chunk.metadata,
        }
    )
    return payload


def ingest_manifest(
    manifest: RagManifest,
    store: RagVectorStore,
    collection_override: str | None = None,
) -> RagIngestionResult:
    collection = collection_override or manifest.collection
    if collection is None:
        raise ValueError("collection must be provided by manifest or override")

    points = build_rag_points(manifest)
    store.ensure_collection(collection, manifest.vector_size, manifest.distance)
    store.upsert_points(collection, points)
    return RagIngestionResult(
        collection=collection,
        manifest_id=manifest.manifest_id,
        manifest_version=manifest.manifest_version,
        vector_size=manifest.vector_size,
        chunk_ids=[point.id for point in points],
        upserted_count=len(points),
    )

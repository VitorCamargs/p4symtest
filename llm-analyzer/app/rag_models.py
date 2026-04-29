from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


RagSourceType = Literal[
    "p4_spec",
    "p4_practice",
    "bmv2",
    "v1model",
    "routing",
    "cisco_manual",
    "iso",
    "paper",
    "project_note",
]
QdrantDistance = Literal["Cosine", "Dot", "Euclid"]


class RagChunk(StrictBaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: RagSourceType
    citation: str = Field(min_length=1)
    version: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0)


class RagManifestChunk(StrictBaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: RagSourceType
    citation: str = Field(min_length=1)
    version: str = Field(min_length=1)
    text: str = Field(min_length=1)
    embedding: list[float] = Field(min_length=1)
    chunk_key: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("embedding")
    @classmethod
    def embedding_values_must_be_finite(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("embedding values must be finite")
        return value

    def as_rag_chunk(self, score: float | None = None) -> RagChunk:
        return RagChunk(
            source_id=self.source_id,
            title=self.title,
            source_type=self.source_type,
            citation=self.citation,
            version=self.version,
            text=self.text,
            score=score,
        )


class RagManifest(StrictBaseModel):
    manifest_version: str = Field(min_length=1)
    manifest_id: str = Field(min_length=1)
    collection: str | None = Field(default=None, min_length=1)
    vector_size: int = Field(gt=0)
    distance: QdrantDistance = "Cosine"
    chunks: list[RagManifestChunk] = Field(min_length=1)

    @model_validator(mode="after")
    def chunk_embeddings_match_vector_size(self) -> "RagManifest":
        mismatched = [
            chunk.source_id
            for chunk in self.chunks
            if len(chunk.embedding) != self.vector_size
        ]
        if mismatched:
            raise ValueError(
                "chunk embedding length must match vector_size for "
                + ", ".join(sorted(mismatched))
            )
        return self


class RagSearchFilters(StrictBaseModel):
    source_ids: list[str] = Field(default_factory=list)
    source_types: list[RagSourceType] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)


class RagSearchRequest(StrictBaseModel):
    query: str = Field(default="", max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)
    query_vector: list[float] | None = None
    filters: RagSearchFilters = Field(default_factory=RagSearchFilters)

    @field_validator("query_vector")
    @classmethod
    def query_vector_values_must_be_finite(
        cls, value: list[float] | None
    ) -> list[float] | None:
        if value is not None and not all(math.isfinite(item) for item in value):
            raise ValueError("query_vector values must be finite")
        return value

    @property
    def normalized_query(self) -> str:
        return " ".join(self.query.split())


class RagSearchResponse(StrictBaseModel):
    chunks: list[RagChunk]
    chunk_ids: list[str]


class RagIngestionResult(StrictBaseModel):
    collection: str
    manifest_id: str
    manifest_version: str
    vector_size: int
    chunk_ids: list[str]
    upserted_count: int

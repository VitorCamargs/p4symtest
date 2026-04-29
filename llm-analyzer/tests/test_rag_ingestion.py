from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.rag import HashingTextEmbedder, RagSearchService
from app.rag_client import InMemoryRagStore
from app.rag_ingestion import ingest_manifest, load_rag_manifest, stable_chunk_id
from app.rag_models import RagChunk, RagSearchRequest


FIXTURE = Path(__file__).parent / "fixtures" / "rag" / "sample_manifest.json"
REQUIRED_CHUNK_FIELDS = {
    "source_id",
    "title",
    "source_type",
    "citation",
    "version",
    "text",
}


def test_rag_ingestion_creates_collection_and_upserts_expected_records() -> None:
    manifest = load_rag_manifest(FIXTURE)
    store = InMemoryRagStore()

    result = ingest_manifest(manifest, store)

    assert result.collection == "rag-test"
    assert result.upserted_count == 2
    assert store.ensure_collection_calls == [("rag-test", 4, "Cosine")]
    assert len(store.upsert_calls) == 1
    assert set(store.collections["rag-test"]) == set(result.chunk_ids)

    first_point = store.collections["rag-test"][result.chunk_ids[0]]
    assert first_point.payload["chunk_id"] == result.chunk_ids[0]
    assert REQUIRED_CHUNK_FIELDS.issubset(first_point.payload)
    assert "embedding" not in first_point.payload


def test_rag_ingestion_is_idempotent_with_stable_chunk_ids() -> None:
    manifest = load_rag_manifest(FIXTURE)
    store = InMemoryRagStore()

    first_result = ingest_manifest(manifest, store)
    second_result = ingest_manifest(manifest, store)

    assert second_result.chunk_ids == first_result.chunk_ids
    assert second_result.upserted_count == first_result.upserted_count
    assert len(store.collections["rag-test"]) == first_result.upserted_count
    assert stable_chunk_id(manifest, manifest.chunks[0], 0) == first_result.chunk_ids[0]


def test_rag_known_query_returns_expected_chunk_from_fake_store() -> None:
    service = _service_with_fixture()

    response = service.search(
        RagSearchRequest(
            query="egress_spec drop behavior",
            limit=1,
            query_vector=[1.0, 0.0, 0.0, 0.0],
        )
    )

    assert len(response.chunks) == 1
    assert response.chunks[0].source_id == "v1model-egress-spec"
    assert response.chunks[0].score == 1.0


def test_rag_empty_query_returns_controlled_empty_result() -> None:
    service = _service_with_fixture()

    response = service.search(
        RagSearchRequest(query="   ", limit=1, query_vector=[1.0, 0.0, 0.0, 0.0])
    )

    assert response.chunks == []
    assert response.chunk_ids == []


def test_rag_search_endpoint_returns_required_payload_fields() -> None:
    app.state.rag_search_service = _service_with_fixture()
    client = TestClient(app)

    response = client.post(
        "/rag/search",
        json={
            "query": "egress_spec drop behavior",
            "limit": 1,
            "query_vector": [1.0, 0.0, 0.0, 0.0],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["chunks"]) == 1
    assert len(body["chunk_ids"]) == 1
    assert REQUIRED_CHUNK_FIELDS.issubset(body["chunks"][0])

    chunk = RagChunk.model_validate(body["chunks"][0])
    assert chunk.source_id == "v1model-egress-spec"
    assert chunk.title
    assert chunk.citation
    assert chunk.version == "fixture-v1"


def test_rag_search_endpoint_filters_payloads() -> None:
    app.state.rag_search_service = _service_with_fixture()
    client = TestClient(app)

    response = client.post(
        "/rag/search",
        json={
            "query": "egress_spec drop behavior",
            "limit": 2,
            "query_vector": [1.0, 0.0, 0.0, 0.0],
            "filters": {
                "source_types": ["p4_practice"],
                "source_ids": [],
                "versions": [],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [chunk["source_id"] for chunk in body["chunks"]] == ["p4-lpm-forwarding"]


def _service_with_fixture() -> RagSearchService:
    manifest = load_rag_manifest(FIXTURE)
    store = InMemoryRagStore()
    ingest_manifest(manifest, store)
    return RagSearchService(
        store=store,
        collection="rag-test",
        embedder=HashingTextEmbedder(vector_size=4),
    )

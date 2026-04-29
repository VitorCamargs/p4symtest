from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.rag_client import QdrantRestClient
from app.rag_ingestion import ingest_manifest, load_rag_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a pre-embedded RAG manifest into Qdrant."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://qdrant:6333"),
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("RAG_COLLECTION"),
        help="Overrides the manifest collection when provided.",
    )
    parser.add_argument(
        "--timeout-seconds",
        default=float(os.getenv("QDRANT_TIMEOUT_SECONDS", "30")),
        type=float,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_rag_manifest(args.manifest)
    client = QdrantRestClient(args.qdrant_url, timeout_seconds=args.timeout_seconds)
    try:
        result = ingest_manifest(manifest, client, collection_override=args.collection)
    finally:
        client.close()

    print(json.dumps(result.model_dump(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

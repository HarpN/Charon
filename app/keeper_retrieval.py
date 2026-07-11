from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import settings
from .embeddings import cosine_similarity, embed_text


class KeeperRetriever:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or settings.keeper_db_path)

    def retrieve(self, query: str, top_k: int | None = None, max_chars: int | None = None) -> list[str]:
        if not self.db_path.exists():
            return []

        limit = top_k or settings.retrieval_top_k
        max_chunk_chars = max_chars or settings.retrieval_max_chars_per_chunk

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    """
                    SELECT kc.text AS text, kce.embedding_json AS embedding_json
                    FROM keeper_chunk_embeddings kce
                    JOIN keeper_chunks kc ON kc.correlation_id = kce.correlation_id AND kc.chunk_index = kce.chunk_index
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

            if not rows:
                try:
                    rows = connection.execute(
                    """
                    SELECT gc.text AS text, gce.embedding_json AS embedding_json
                    FROM guide_chunk_embeddings gce
                    JOIN guide_chunks gc ON gc.job_id = gce.job_id AND gc.chunk_index = gce.chunk_index
                    """
                    ).fetchall()
                except sqlite3.OperationalError:
                    return []

        if not rows:
            return []

        query_vector = embed_text(query)
        ranked: list[tuple[float, str]] = []
        for row in rows:
            try:
                embedding = json.loads(row["embedding_json"])
            except json.JSONDecodeError:
                continue
            score = cosine_similarity(query_vector, embedding)
            ranked.append((score, str(row["text"])))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [text[:max_chunk_chars] for _, text in ranked[:limit]]

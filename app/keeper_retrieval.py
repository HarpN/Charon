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
            rows: list[sqlite3.Row] = []
            trust_column_available = False

            try:
                chunk_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(keeper_chunks)").fetchall()
                }
                trust_column_available = "trust_status" in chunk_columns
            except sqlite3.OperationalError:
                trust_column_available = False
            link_tables_available = True
            has_links = False

            try:
                has_links = connection.execute(
                    "SELECT COUNT(*) AS total FROM keeper_game_guide_links"
                ).fetchone()["total"] > 0
            except sqlite3.OperationalError:
                link_tables_available = False

            if link_tables_available and has_links:
                if trust_column_available:
                    rows = connection.execute(
                        """
                        SELECT
                            kc.text AS text,
                            kce.embedding_json AS embedding_json,
                            kgl.match_confidence AS match_confidence
                        FROM keeper_game_guide_links kgl
                        JOIN keeper_chunks kc
                            ON kc.guide_url = kgl.guide_url
                           AND kc.game_title = kgl.game_title
                        JOIN keeper_chunk_embeddings kce
                            ON kce.correlation_id = kc.correlation_id
                           AND kce.chunk_index = kc.chunk_index
                        WHERE kgl.match_confidence >= ?
                          AND kc.trust_status = 'approved'
                        """,
                        (float(settings.retrieval_link_min_confidence),),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT
                            kc.text AS text,
                            kce.embedding_json AS embedding_json,
                            kgl.match_confidence AS match_confidence
                        FROM keeper_game_guide_links kgl
                        JOIN keeper_chunks kc
                            ON kc.guide_url = kgl.guide_url
                           AND kc.game_title = kgl.game_title
                        JOIN keeper_chunk_embeddings kce
                            ON kce.correlation_id = kc.correlation_id
                           AND kce.chunk_index = kc.chunk_index
                        WHERE kgl.match_confidence >= ?
                        """,
                        (float(settings.retrieval_link_min_confidence),),
                    ).fetchall()

                # When links exist but none meet confidence threshold, avoid degrading to low-confidence retrieval.
                if not rows:
                    return []

            try:
                if not rows:
                    if trust_column_available:
                        rows = connection.execute(
                            """
                            SELECT kc.text AS text, kce.embedding_json AS embedding_json, 0.0 AS match_confidence
                            FROM keeper_chunk_embeddings kce
                            JOIN keeper_chunks kc ON kc.correlation_id = kce.correlation_id AND kc.chunk_index = kce.chunk_index
                            WHERE kc.trust_status = 'approved'
                            """
                        ).fetchall()
                    else:
                        rows = connection.execute(
                            """
                            SELECT kc.text AS text, kce.embedding_json AS embedding_json, 0.0 AS match_confidence
                            FROM keeper_chunk_embeddings kce
                            JOIN keeper_chunks kc ON kc.correlation_id = kce.correlation_id AND kc.chunk_index = kce.chunk_index
                            """
                        ).fetchall()
            except sqlite3.OperationalError:
                rows = []

            if not rows:
                return []

        if not rows:
            return []

        query_vector = embed_text(query)
        ranked: list[tuple[float, float, str]] = []
        for row in rows:
            try:
                embedding = json.loads(row["embedding_json"])
            except json.JSONDecodeError:
                continue
            semantic_score = cosine_similarity(query_vector, embedding)
            confidence = float(row["match_confidence"])
            ranked.append((confidence, semantic_score, str(row["text"])))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [text[:max_chunk_chars] for _, _, text in ranked[:limit]]

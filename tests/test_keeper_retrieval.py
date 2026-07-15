from __future__ import annotations

import json
import sqlite3

from app.config import settings
from app.embeddings import embed_text
from app.keeper_retrieval import KeeperRetriever


def _seed_keeper_rows(db_path: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE keeper_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                guide_url TEXT NOT NULL,
                game_title TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL,
                text TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                trust_status TEXT NOT NULL DEFAULT 'approved'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE keeper_chunk_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding_json TEXT NOT NULL,
                UNIQUE(correlation_id, chunk_index)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE keeper_game_guide_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_title TEXT NOT NULL,
                platform TEXT NOT NULL,
                guide_url TEXT NOT NULL,
                match_confidence REAL NOT NULL,
                score_views REAL NOT NULL DEFAULT 0,
                score_recency REAL NOT NULL DEFAULT 0,
                score_total REAL NOT NULL DEFAULT 0,
                match_mode TEXT NOT NULL DEFAULT 'probabilistic',
                linked_at TEXT NOT NULL,
                UNIQUE(game_title, platform, guide_url)
            )
            """
        )

        high_text = "Astro Bot cleanup route with hidden bot checklist and efficient chapter-select path."
        low_text = "Completely unrelated text for a weakly matched guide that still contains cleanup words."

        for correlation_id, guide_url, game_title, text in [
            ("cid-high", "https://example.org/high", "Astro Bot", high_text),
            ("cid-low", "https://example.org/low", "Astro Bot", low_text),
        ]:
            connection.execute(
                """
                INSERT INTO keeper_chunks (
                    source_agent, guide_url, game_title, correlation_id, fetched_at,
                    chunk_index, heading, text, token_count, trust_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("milo", guide_url, game_title, correlation_id, "2026-07-11T00:00:00+00:00", 0, "Section 1", text, len(text.split()), "approved"),
            )
            connection.execute(
                """
                INSERT INTO keeper_chunk_embeddings (
                    source_agent, correlation_id, chunk_index, embedding_json
                ) VALUES (?, ?, ?, ?)
                """,
                ("milo", correlation_id, 0, json.dumps(embed_text(text), separators=(",", ":"))),
            )

        connection.execute(
            """
            INSERT INTO keeper_game_guide_links (
                game_title, platform, guide_url, match_confidence,
                score_views, score_recency, score_total, match_mode, linked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Astro Bot", "PS5", "https://example.org/high", 0.93, 0.9, 0.9, 0.93, "probabilistic", "2026-07-11T00:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO keeper_game_guide_links (
                game_title, platform, guide_url, match_confidence,
                score_views, score_recency, score_total, match_mode, linked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Astro Bot", "PS5", "https://example.org/low", 0.31, 0.2, 0.2, 0.31, "probabilistic", "2026-07-11T00:00:00+00:00"),
        )


def test_retrieval_prefers_high_confidence_links(tmp_path, monkeypatch) -> None:
    keeper_db = tmp_path / "keeper_retrieval.db"
    _seed_keeper_rows(str(keeper_db))
    monkeypatch.setattr(settings, "retrieval_link_min_confidence", 0.25)

    retriever = KeeperRetriever(db_path=str(keeper_db))
    snippets = retriever.retrieve("cleanup trophies in astro bot", top_k=2)

    assert len(snippets) == 2
    assert "hidden bot checklist" in snippets[0]


def test_retrieval_filters_low_confidence_links(tmp_path, monkeypatch) -> None:
    keeper_db = tmp_path / "keeper_retrieval_threshold.db"
    _seed_keeper_rows(str(keeper_db))
    monkeypatch.setattr(settings, "retrieval_link_min_confidence", 0.8)

    retriever = KeeperRetriever(db_path=str(keeper_db))
    snippets = retriever.retrieve("cleanup trophies in astro bot", top_k=5)

    assert len(snippets) == 1
    assert "hidden bot checklist" in snippets[0]


def test_retrieval_falls_back_without_link_table(tmp_path, monkeypatch) -> None:
    keeper_db = tmp_path / "keeper_retrieval_fallback.db"
    with sqlite3.connect(keeper_db) as connection:
        connection.execute(
            """
            CREATE TABLE keeper_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                guide_url TEXT NOT NULL,
                game_title TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL,
                text TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                trust_status TEXT NOT NULL DEFAULT 'approved'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE keeper_chunk_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding_json TEXT NOT NULL,
                UNIQUE(correlation_id, chunk_index)
            )
            """
        )
        text = "Fallback retrieval text for keeper without linker tables."
        connection.execute(
            """
            INSERT INTO keeper_chunks (
                source_agent, guide_url, game_title, correlation_id, fetched_at,
                chunk_index, heading, text, token_count, trust_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("milo", "https://example.org/fallback", "Astro Bot", "cid-fallback", "2026-07-11T00:00:00+00:00", 0, "Section 1", text, 8, "approved"),
        )
        connection.execute(
            """
            INSERT INTO keeper_chunk_embeddings (
                source_agent, correlation_id, chunk_index, embedding_json
            ) VALUES (?, ?, ?, ?)
            """,
            ("milo", "cid-fallback", 0, json.dumps(embed_text(text), separators=(",", ":"))),
        )

    monkeypatch.setattr(settings, "retrieval_link_min_confidence", 0.8)
    retriever = KeeperRetriever(db_path=str(keeper_db))
    snippets = retriever.retrieve("fallback retrieval", top_k=1)

    assert len(snippets) == 1
    assert "Fallback retrieval text" in snippets[0]


def test_retrieval_excludes_unapproved_chunks(tmp_path, monkeypatch) -> None:
    keeper_db = tmp_path / "keeper_retrieval_unapproved.db"
    with sqlite3.connect(keeper_db) as connection:
        connection.execute(
            """
            CREATE TABLE keeper_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                guide_url TEXT NOT NULL,
                game_title TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL,
                text TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                trust_status TEXT NOT NULL DEFAULT 'approved'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE keeper_chunk_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_agent TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding_json TEXT NOT NULL,
                UNIQUE(correlation_id, chunk_index)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO keeper_chunks (
                source_agent, guide_url, game_title, correlation_id, fetched_at,
                chunk_index, heading, text, token_count, trust_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "milo",
                "https://example.org/unapproved",
                "Astro Bot",
                "cid-unapproved",
                "2026-07-11T00:00:00+00:00",
                0,
                "Section 1",
                "This chunk should never be returned to Charon retrieval.",
                9,
                "rejected",
            ),
        )
        connection.execute(
            """
            INSERT INTO keeper_chunk_embeddings (
                source_agent, correlation_id, chunk_index, embedding_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "milo",
                "cid-unapproved",
                0,
                json.dumps(embed_text("This chunk should never be returned to Charon retrieval."), separators=(",", ":")),
            ),
        )

    monkeypatch.setattr(settings, "retrieval_link_min_confidence", 0.0)
    retriever = KeeperRetriever(db_path=str(keeper_db))
    snippets = retriever.retrieve("astro bot cleanup", top_k=3)

    assert snippets == []

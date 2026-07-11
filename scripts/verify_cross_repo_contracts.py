from __future__ import annotations

import argparse
from pathlib import Path


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def require_tokens(label: str, text: str, tokens: list[str]) -> list[str]:
    failures: list[str] = []
    for token in tokens:
        if token not in text:
            failures.append(f"[{label}] missing token: {token}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify cross-repo schema and contract invariants.")
    parser.add_argument("--sly-root", default="../sly", help="Path to sly repository root")
    parser.add_argument("--milo-root", default="../milo", help="Path to milo repository root")
    parser.add_argument("--keeper-root", default="../TheKeeper", help="Path to TheKeeper repository root")
    parser.add_argument("--charon-root", default=".", help="Path to charon repository root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sly_root = Path(args.sly_root)
    milo_root = Path(args.milo_root)
    keeper_root = Path(args.keeper_root)
    charon_root = Path(args.charon_root)

    failures: list[str] = []

    sly_keeper_export = read_text(sly_root / "app" / "keeper_export.py")
    failures.extend(
        require_tokens(
            "sly keeper export",
            sly_keeper_export,
            [
                "CREATE TABLE IF NOT EXISTS keeper_games",
                "CREATE TABLE IF NOT EXISTS keeper_snapshots",
                "version_label IN ('LATEST', 'PREVIOUS', 'STABLE')",
                "INSERT OR REPLACE INTO keeper_snapshots",
                "VALUES (?, ?, 'PREVIOUS', ?, ?)",
                "VALUES (?, ?, 'LATEST', ?, ?)",
                '"completion_rate": float(telemetry.completion)',
                '"trophy_count": int(telemetry.trophies_total)',
                '"correlation_id": telemetry.correlation_id',
            ],
        )
    )

    milo_storage = read_text(milo_root / "app" / "storage.py")
    failures.extend(
        require_tokens(
            "milo keeper export",
            milo_storage,
            [
                "CREATE TABLE IF NOT EXISTS keeper_guides",
                "quality_views INTEGER NOT NULL DEFAULT 0",
                "quality_age_days INTEGER NOT NULL DEFAULT 0",
                "quality_score REAL NOT NULL DEFAULT 0",
                "CREATE TABLE IF NOT EXISTS keeper_snapshots",
                "VALUES (?, ?, 'PREVIOUS', ?, ?)",
                "VALUES (?, ?, 'LATEST', ?, ?)",
                '"quality_views": int(guide_document.quality_views)',
                '"quality_age_days": int(guide_document.quality_age_days)',
                '"quality_score": float(guide_document.quality_score)',
                '"chunk_count": len(guide_document.chunks)',
            ],
        )
    )

    keeper_linker = read_text(keeper_root / "scripts" / "run_linker.py")
    failures.extend(
        require_tokens(
            "keeper linker",
            keeper_linker,
            [
                "CREATE TABLE IF NOT EXISTS keeper_game_guide_links",
                "match_confidence REAL NOT NULL",
                "score_views REAL NOT NULL DEFAULT 0",
                "score_recency REAL NOT NULL DEFAULT 0",
                "score_total REAL NOT NULL DEFAULT 0",
                "SELECT game_title, platform FROM keeper_games",
                "SELECT guide_url, game_title, platform, quality_views, quality_age_days, quality_score FROM keeper_guides",
            ],
        )
    )

    keeper_discrepancy = read_text(keeper_root / "scripts" / "discrepancy_workflow.py")
    failures.extend(
        require_tokens(
            "keeper discrepancy workflow",
            keeper_discrepancy,
            [
                "VALID_STATUSES = {\"PENDING_USER\", \"CONFIRMED\", \"DISMISSED\"}",
                "def scan_discrepancies",
                "def resolve_discrepancy",
                "--decision",
                "CONFIRMED",
                "DISMISSED",
            ],
        )
    )

    charon_config = read_text(charon_root / "app" / "config.py")
    failures.extend(
        require_tokens(
            "charon config",
            charon_config,
            [
                "retrieval_link_min_confidence",
                "RETRIEVAL_LINK_MIN_CONFIDENCE",
            ],
        )
    )

    charon_retrieval = read_text(charon_root / "app" / "keeper_retrieval.py")
    failures.extend(
        require_tokens(
            "charon retrieval",
            charon_retrieval,
            [
                "keeper_game_guide_links",
                "match_confidence >= ?",
                "settings.retrieval_link_min_confidence",
                "if not rows:\n                    return []",
                "ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)",
            ],
        )
    )

    if failures:
        print("Contract verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Contract verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

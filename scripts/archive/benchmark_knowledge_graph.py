#!/usr/bin/env python3
"""
Knowledge graph performance benchmark (scaling check).

Creates a temporary SQLite knowledge DB, loads N synthetic discoveries, then runs:
- indexed filter query
- FTS query (if available)
- similar-discoveries (tag overlap)

Usage:
  python3 scripts/benchmark_knowledge_graph.py --n 10000
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import string
import time
from pathlib import Path


def _rand_words(k: int) -> str:
    return " ".join(
        "".join(random.choice(string.ascii_lowercase) for _ in range(random.randint(3, 10)))
        for _ in range(k)
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000, help="Number of synthetic discoveries to insert")
    parser.add_argument("--db", type=str, default="data/bench_knowledge.db", help="DB path (will be overwritten)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    repo_root = Path(__file__).resolve().parent.parent
    db_path = (repo_root / args.db).resolve()
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    # Force sqlite backend for this run (but do not touch the main data/knowledge.db)
    os.environ["UNITARES_KNOWLEDGE_DB_PATH"] = str(db_path)

    from src.knowledge_db import KnowledgeGraphDB
    from src.knowledge_graph import DiscoveryNode

    graph = KnowledgeGraphDB(db_path=db_path, enable_embeddings=False)

    tag_pool = [f"tag{i}" for i in range(200)]
    agent_pool = [f"bench_agent_{i}" for i in range(50)]
    types = ["bug_found", "insight", "pattern", "improvement", "question", "answer", "note"]

    print(f"DB: {db_path}")
    print(f"Loading N={args.n} synthetic discoveries...")

    t0 = time.perf_counter()
    for i in range(args.n):
        d = DiscoveryNode(
            id=f"bench:{i}",
            agent_id=random.choice(agent_pool),
            type=random.choice(types),
            summary=_rand_words(12),
            details=_rand_words(40),
            tags=random.sample(tag_pool, k=random.randint(1, 6)),
            severity=None,
        )
        await graph.add_discovery(d)
    load_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Insert: {args.n} rows in {load_ms:.1f}ms ({(load_ms / max(args.n,1)):.3f}ms/op)")

    # 1) Indexed filter query
    t1 = time.perf_counter()
    out = await graph.query(agent_id=agent_pool[0], limit=50)
    q1_ms = (time.perf_counter() - t1) * 1000.0
    print(f"Query (agent_id filter, limit=50): {q1_ms:.2f}ms (returned={len(out)})")

    # 2) FTS query (best-effort): pick a word from a recent summary
    t2 = time.perf_counter()
    fts_ms = None
    try:
        word = out[0].summary.split()[0] if out else "sqlite"
        hits = await graph.full_text_search(word, limit=50)
        fts_ms = (time.perf_counter() - t2) * 1000.0
        print(f"FTS (query='{word}', limit=50): {fts_ms:.2f}ms (returned={len(hits)})")
    except Exception as e:
        print(f"FTS: unavailable/error: {e}")

    # 3) Similar discovery lookup
    t3 = time.perf_counter()
    sim = await graph.find_similar(out[0], limit=10) if out else []
    sim_ms = (time.perf_counter() - t3) * 1000.0
    print(f"find_similar(limit=10): {sim_ms:.2f}ms (returned={len(sim)})")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))



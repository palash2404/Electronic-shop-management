"""Shared test setup: every test runs on a temporary copy of the database."""
import pytest

import db
import kg.store


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "eshop.db")
    monkeypatch.setattr(kg.store, "DATA_PATH", tmp_path / "data.ttl")
    monkeypatch.setattr(kg.store, "sync_neo4j", lambda graph: "Neo4j skipped in tests.")
    db.init_db()

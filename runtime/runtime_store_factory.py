"""RuntimeStoreFactory — single controlled entry point for all persistent stores.

Resolves database path from runtime profile + namespace.
Guarantees same (profile, namespace, sessionId) → same store instances.
Enforces test/production isolation.

Production workflow NEVER receives dbPath. The factory resolves it from env.
Test isolation uses AWP_RUNTIME_PROFILE=test + AWP_TEST_RUNTIME_NAMESPACE.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from ..storage.sqlite.database import Database
from .session_runtime_registry import SessionRuntimeStoreRegistry


# Module-level singleton cache keyed by (thread_id, db_path).
#
# sqlite3 connections are thread-affine by default. The management API can run
# dispatcher work in a background thread while UI list/read endpoints stay on
# the aiohttp event loop thread, so each thread needs its own connection-backed
# registry for the same database path.
_registry_cache: dict[tuple[int, str], SessionRuntimeStoreRegistry] = {}
_cache_lock = threading.Lock()


def _resolve_db_path(profile: str, namespace: str, store_root: str = "") -> str:
    """Resolve database path from profile + namespace.

    Production: awp_rp_runtime.db in current directory.
    Test: <store_root>/<namespace>/awp_session.db
    """
    if profile == "test":
        if not store_root:
            store_root = str(Path("artifacts") / "test-runtime")
        db_dir = Path(store_root) / namespace
        db_dir.mkdir(parents=True, exist_ok=True)
        return str(db_dir / "awp_session.db")

    # Production: no namespace, no user-controlled path
    explicit = os.environ.get("AWP_RUNTIME_DB_PATH", "")
    if explicit:
        return explicit
    return "awp_rp_runtime.db"


def _get_or_create_registry(db_path: str) -> SessionRuntimeStoreRegistry:
    """Get or create a registry for the given database path. Thread-safe."""
    cache_key = (threading.get_ident(), db_path)
    with _cache_lock:
        if cache_key not in _registry_cache:
            db = Database(db_path)
            db.initialize()
            _registry_cache[cache_key] = SessionRuntimeStoreRegistry(db)
        return _registry_cache[cache_key]


def clear_registry_cache() -> None:
    """Clear all cached registries (for testing)."""
    with _cache_lock:
        for registry in _registry_cache.values():
            registry.db.close()
        _registry_cache.clear()


class RuntimeStoreFactory:
    """Controlled factory for persistent SQLite stores.

    Usage:
        # Production (env-driven):
        factory = RuntimeStoreFactory.from_env()
        registry = factory.registry

        # Test (explicit namespace):
        factory = RuntimeStoreFactory.for_test("run_001", store_root="/tmp/test")
        registry = factory.registry
    """

    def __init__(self, profile: str, namespace: str, db_path: str):
        self._profile = profile
        self._namespace = namespace
        self._db_path = db_path
        self._registry = _get_or_create_registry(db_path)

    @classmethod
    def from_env(cls) -> RuntimeStoreFactory:
        """Create factory from environment variables.

        Production: AWP_RUNTIME_PROFILE=production (default)
        Test: AWP_RUNTIME_PROFILE=test + AWP_TEST_RUNTIME_NAMESPACE
        """
        profile = os.environ.get("AWP_RUNTIME_PROFILE", "production")
        namespace = os.environ.get("AWP_TEST_RUNTIME_NAMESPACE", "default")
        store_root = os.environ.get("AWP_TEST_STORE_ROOT", "")
        db_path = _resolve_db_path(profile, namespace, store_root)
        return cls(profile, namespace, db_path)

    @classmethod
    def for_test(
        cls,
        namespace: str,
        store_root: str = "",
    ) -> RuntimeStoreFactory:
        """Create a test-scoped factory. Always uses test profile."""
        if not store_root:
            store_root = str(Path("artifacts") / "test-runtime")
        db_path = _resolve_db_path("test", namespace, store_root)
        return cls("test", namespace, db_path)

    @classmethod
    def for_production(cls) -> RuntimeStoreFactory:
        """Create a production factory. Ignores test env vars."""
        db_path = _resolve_db_path("production", "", "")
        return cls("production", "", db_path)

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def registry(self) -> SessionRuntimeStoreRegistry:
        return self._registry

    # ── Convenience accessors ─────────────────────────────────────────────

    @property
    def card_state_store(self):
        return self._registry.card_state_store

    @property
    def turn_record_store(self):
        return self._registry.turn_record_store

    @property
    def round_snapshot_store(self):
        return self._registry.round_snapshot_store

    @property
    def active_memory_store(self):
        return self._registry.active_memory_store

    @property
    def rag_memory_store(self):
        return self._registry.rag_memory_store

    @property
    def trace_store(self):
        return self._registry.trace_store

    @property
    def card_session_binding_store(self):
        return self._registry.card_session_binding_store

    @property
    def opening_record_store(self):
        return self._registry.opening_record_store

    @property
    def worldbook_binding_store(self):
        return self._registry.worldbook_binding_store

    @property
    def bootstrap_receipt_store(self):
        return self._registry.bootstrap_receipt_store

    def close(self) -> None:
        """Close the underlying database connection."""
        self._registry.db.close()

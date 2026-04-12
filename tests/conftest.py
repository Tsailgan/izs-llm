"""
tests/conftest.py
Session-scoped fixtures for the IZS test suite.

IMPORTANT: This file loads .env BEFORE any app imports.
In Docker, docker-compose reads .env natively. But when running
pytest locally (or in CI), we need to explicitly load it.

Validates:
  - MISTRAL_API_KEY is set (hard fail without it)
  - GROQ_API_KEY is set (soft warning — tests run without judge)
  - FAISS index exists (hard fail — RAG won't work without it)
"""
import os
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# 1. Load .env BEFORE any app/test imports
# ──────────────────────────────────────────────────────────────
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).parent.parent
_env_path = PROJECT_DIR / ".env"

if _env_path.exists():
    load_dotenv(_env_path, override=False)  # don't override existing env vars
    print(f"✅ Loaded .env from {_env_path}")
else:
    print(f"⚠️  No .env file found at {_env_path} — relying on environment variables")


# ──────────────────────────────────────────────────────────────
# 2. Validate required environment BEFORE heavy imports
# ──────────────────────────────────────────────────────────────
def _preflight_checks():
    """Fail fast with clear messages instead of cryptic 401s."""
    errors = []

    # --- MISTRAL_API_KEY (required — powers the agent) ---
    if not os.environ.get("MISTRAL_API_KEY"):
        errors.append(
            "MISTRAL_API_KEY is not set.\n"
            "  → Add it to .env or export it: export MISTRAL_API_KEY=your_key"
        )

    # --- GROQ_API_KEY (optional — powers the judge) ---
    if not os.environ.get("GROQ_API_KEY"):
        print(
            "\n⚠️  GROQ_API_KEY is not set — LLM judge scoring will be SKIPPED.\n"
            "   Tests will still run with deterministic assertions only.\n"
        )

    # --- FAISS index (required — RAG retrieval) ---
    from app.core.config import settings
    faiss_path = Path(settings.FAISS_INDEX_PATH)
    if not faiss_path.exists():
        errors.append(
            f"FAISS index not found at: {faiss_path}\n"
            f"  → Run the indexing script first, or check DATA_DIR"
        )

    if errors:
        print("\n" + "=" * 60)
        print("❌ PREFLIGHT CHECK FAILED — Cannot run tests")
        print("=" * 60)
        for e in errors:
            print(f"\n  • {e}")
        print()
        sys.exit(1)

    print("✅ Preflight checks passed")


_preflight_checks()


# ──────────────────────────────────────────────────────────────
# 3. Now safe to import the app and test utilities
# ──────────────────────────────────────────────────────────────
import pytest
from fastapi.testclient import TestClient

from app.api import app
from tests.report import report


@pytest.fixture(scope="session")
def api_client():
    """In-memory API client with lifespan (loads RAG catalog)."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def finalize_report(request):
    """Save the markdown report after all tests complete."""
    yield
    report_path = report.save_report()
    print(f"\n📋 Final report saved to: {report_path}")

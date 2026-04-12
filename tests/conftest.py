"""
tests/conftest.py
Session-scoped fixtures for the IZS test suite.
Configures FastAPI TestClient and report finalization.
"""
import pytest
from fastapi.testclient import TestClient

from app.api import app
from tests.report import report

@pytest.fixture(scope="session")
def api_client():
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session", autouse=True)
def finalize_report(request):
    """Save the markdown report after all tests complete."""
    yield
    report_path = report.save_report()
    print(f"\n📋 Final report saved to: {report_path}")

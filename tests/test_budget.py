import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.request_budget import RequestBudget


def test_budget_counts_failed_attempts_and_releases_concurrency():
    async def run():
        budget = RequestBudget()
        await budget.enter(2, 1)
        with pytest.raises(HTTPException):
            await budget.enter(2, 1)
        await budget.leave()
        await budget.enter(2, 1)
        await budget.leave()
        with pytest.raises(HTTPException):
            await budget.enter(2, 1)
    asyncio.run(run())


def test_readiness_fails_without_credentials_or_with_paid_model():
    config = Settings(_env_file=None, llm_provider="openrouter", llm_model="openrouter/free")
    app.dependency_overrides[get_settings] = lambda: config
    try:
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 503
            config.openrouter_api_key = "unit-test-key"
            config.internal_service_token = "x" * 48
            assert client.get("/ready").status_code == 200
            config.llm_model = "paid/model"
            assert client.get("/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()

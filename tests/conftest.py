"""Shared test fixtures for llouie."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def load_json_fixture(name: str):
    return json.loads(load_fixture(name))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def fx_v1_models() -> dict:
    return load_json_fixture("v1_models.json")


@pytest.fixture
def fx_running_idle() -> dict:
    return load_json_fixture("running_idle.json")


@pytest.fixture
def fx_running_one_loaded() -> dict:
    return load_json_fixture("running_one_loaded.json")


@pytest.fixture
def fx_api_metrics_empty() -> list:
    return load_json_fixture("api_metrics_empty.json")


@pytest.fixture
def fx_api_metrics_populated() -> list:
    return load_json_fixture("api_metrics_populated.json")


@pytest.fixture
def fx_slots_idle() -> list:
    return load_json_fixture("slots_idle.json")


@pytest.fixture
def fx_slots_one_processing() -> list:
    return load_json_fixture("slots_one_processing.json")


@pytest.fixture
def fx_ps_idle() -> str:
    return load_fixture("ps_idle.txt")


@pytest.fixture
def fx_ps_one_loaded() -> str:
    return load_fixture("ps_one_loaded.txt")

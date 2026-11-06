"""Shared fixtures: every test runs against an isolated temporary data root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REAL_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def data_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("flymind-data")
    (root / "processed").mkdir()
    os.environ["FLYMIND_DATA_DIR"] = str(root)
    os.environ["FLYMIND_EXPERIMENTS_DIR"] = str(tmp_path_factory.mktemp("experiments"))
    from flymind.connectome.fixtures import build_fixture
    from flymind.connectome.store import clear_store_cache

    build_fixture(root / "processed")
    clear_store_cache()
    return root


@pytest.fixture(scope="session")
def store(data_root):
    from flymind.connectome.store import get_store

    return get_store("synthetic_demo_v1")


@pytest.fixture(scope="session")
def group(store):
    """group("orn_attr_l") -> dataset idx of a named fixture group."""
    from flymind.connectome.selectors import NeuronSelector, resolve

    return lambda name: resolve(store, NeuronSelector(group=name))


@pytest.fixture(scope="session")
def rendering():
    """Skip a test when MuJoCo cannot create an OpenGL context (e.g. GPU-less CI VMs)."""
    import mujoco

    try:
        mujoco.Renderer(mujoco.MjModel.from_xml_string("<mujoco/>"), 8, 8).close()
    except Exception as exc:  # pragma: no cover - environment specific
        pytest.skip(f"no OpenGL context for MuJoCo rendering: {type(exc).__name__}: {exc}")


@pytest.fixture(scope="session")
def real_store():
    """The real FlyWire v783 dataset, if the developer has imported it."""
    from flymind.connectome.store import ConnectomeStore, DatasetNotFoundError

    try:
        return ConnectomeStore.open("flywire_fafb_783", root=REAL_DATA_ROOT / "processed")
    except DatasetNotFoundError:
        pytest.skip("FlyWire v783 not imported (run `make data-flywire`)")

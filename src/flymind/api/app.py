"""FastAPI application factory."""

from __future__ import annotations

import importlib.util
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from flymind import __version__
from flymind.api import routes_data, routes_experiments, routes_fly, routes_sim
from flymind.api.common import SafeJSONResponse
from flymind.api.state import ServiceState
from flymind.common.logging import configure_logging, get_logger
from flymind.common.paths import repo_root
from flymind.common.provenance import git_commit, machine_info, package_versions
from flymind.connectome.store import list_datasets
from flymind.visualization import geometry

log = get_logger("api")
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = ServiceState()
    log.info("FlyMind API started", extra={"version": __version__})
    yield
    app.state.service.shutdown()


def create_app() -> FastAPI:
    configure_logging(
        os.environ.get("FLYMIND_LOG_LEVEL", "INFO"),
        json_output=os.environ.get("FLYMIND_LOG_JSON", "1") == "1",
    )
    app = FastAPI(
        title="FlyMind API",
        version=__version__,
        lifespan=lifespan,
        default_response_class=SafeJSONResponse,
        description="Connectome simulation, virtual fly and 3D explorer backend.",
    )
    origins = [
        o.strip()
        for o in os.environ.get("FLYMIND_CORS_ORIGINS", DEFAULT_ORIGINS).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Count", "X-Units"],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/system")
    def system():
        ds = list_datasets()
        skel = (geometry.skeleton_store_dir() / "skeleton_index.npz").is_file()
        return {
            "version": __version__,
            "git_commit": git_commit(),
            "packages": package_versions(),
            "machine": machine_info(),
            "capabilities": {
                "flygym": importlib.util.find_spec("flygym") is not None,
                "mujoco": importlib.util.find_spec("mujoco") is not None,
                "brian2": importlib.util.find_spec("brian2") is not None,
                "torch": importlib.util.find_spec("torch") is not None,
                "skeletons_installed": skel,
            },
            "datasets": [
                {
                    "dataset_id": m.dataset_id,
                    "synthetic": m.synthetic,
                    "validation_status": m.validation_status,
                    "n_neurons": m.n_neurons,
                }
                for m in ds
            ],
            "full_brain_available": any(m.dataset_id == "flywire_fafb_783" for m in ds),
        }

    app.include_router(routes_data.router)
    app.include_router(routes_sim.router)
    app.include_router(routes_sim.ws_router)
    app.include_router(routes_fly.router)
    app.include_router(routes_fly.ws_router)
    app.include_router(routes_experiments.router)

    dist = repo_root() / "apps" / "web" / "dist"
    if dist.is_dir():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith(("api/", "ws/")) or path in ("api", "ws"):
                raise HTTPException(404, f"no API route /{path}")
            target = (dist / path).resolve()
            if path and dist.resolve() in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()

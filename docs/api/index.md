# API

The FastAPI service (`uv run flymind serve`, default `http://127.0.0.1:8000`) publishes
an OpenAPI schema at `/openapi.json` and interactive docs at `/docs`. All root IDs are
JSON **strings**.

| Area | Endpoints |
|---|---|
| System | `GET /api/health`, `GET /api/system`, `GET /api/evidence`, `GET /api/brain/params` |
| Datasets | `GET /api/datasets`, `GET /api/datasets/{id}`, `GET /api/datasets/{id}/validation`, `GET /api/sources` |
| Neurons | `GET /api/datasets/{id}/neurons?q=&super_class=&cell_type=&side=&nt_type=&neuropil=&limit=&offset=`, `GET …/neurons/{root_id}`, `GET …/index/{idx}`, `GET …/neurons/{root_id}/partners?direction=&min_syn=&limit=` |
| Connectivity | `GET …/pathways?source=&target=&min_syn=&max_depth=`, `GET …/subgraph?seeds=&depth=&direction=&min_syn=&max_nodes=&format=json|csv` |
| Geometry | `GET …/points` (float32 µm, binary), `GET …/attributes/{field}`, `GET …/neuropils`, `GET …/skeletons/{root_id}?lod=0..2` |
| Groups | `GET …/groups`, `POST …/groups` |
| Simulation | `POST /api/sim/sessions`, `GET /api/sim/sessions[/{id}]`, `DELETE …/{id}`, `POST …/{id}/control` (`start|pause|resume|stop|reset|step|speed`), `POST/DELETE …/{id}/stimuli[/{sid}]`, `POST/DELETE …/{id}/interventions[/{iid}]`, `POST …/interventions/clear`, `POST …/probes`, `GET …/activity`, `GET …/raster`, `GET …/traces`, `GET …/population`, `GET …/export?format=parquet|csv|json`, `POST …/save`; WebSocket `/ws/sim/{id}` |
| Virtual fly | `GET /api/fly/arenas`, `GET /api/fly/bridges`, `POST /api/fly/odor-field`, `GET /api/fly/meshes/{meta,data}`, `POST /api/fly/sessions`, `GET/DELETE …/{id}`, `POST …/{id}/control`, `POST …/{id}/baseline`, `GET …/{id}/trajectory`, `POST …/{id}/save`, `GET /api/fly/recordings[/{rid}]`; WebSocket `/ws/fly/{id}` |
| Experiments | `GET /api/experiments/templates`, `POST /api/experiments/run`, `GET /api/experiments[/{id}]`, `GET …/{id}/files/{name}`, `GET …/{id}/runs/{run}/trajectory`, `POST /api/experiments/compare`, `GET /api/jobs[/{id}]`, `POST /api/jobs/{id}/cancel` |

WebSocket clients may send `{"interval_ms": 100, "max_spikes": 20000}` to the simulation
socket to set the aggregation interval and spike cap.

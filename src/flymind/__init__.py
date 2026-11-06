"""FlyMind: connectome-constrained Drosophila simulation, virtual fly and 3D brain explorer.

Package layout (layered; lower layers never import higher ones, enforced by
``tests/unit/test_architecture.py``):

    common        -> paths, logging, provenance, evidence categories
    connectome    -> dataset adapters, canonical storage, sparse graph, validation
    brain         -> leaky integrate-and-fire engines, stimulation, recording
    visualization -> anatomy geometry (skeletons, meshes) for the 3D explorer
    embodiment    -> FlyGym/MuJoCo body, arenas, sensors, neural-motor bridge
    experiments   -> reproducible experiment specs, runner, persistence
    api / cli     -> FastAPI service and command-line interface
"""

__version__ = "0.1.0"

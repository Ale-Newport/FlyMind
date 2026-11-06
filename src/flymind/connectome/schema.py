"""Canonical, dataset-independent connectome schema.

Every adapter converts its source files into exactly these tables, so that the
simulator, the 3D explorer and the virtual fly all consume one representation.

Identifier rules (see docs/scientific/connectome-sources.md):

* ``root_id`` is the source dataset's neuron identifier, always stored as int64.
  FlyWire root IDs exceed 2**53 and are silently corrupted by float64, so readers
  must never let pandas infer them as floats (adapters read them as strings first).
* ``idx`` is a dense 0..N-1 index assigned by sorting ``root_id`` ascending. It is a
  storage detail, deterministic for a given neuron set, and never shown as an ID.
"""

from __future__ import annotations

import pyarrow as pa

# Neurotransmitter labels used across FlyMind. Source datasets use different
# spellings; adapters normalise to these.
NT_TYPES = ("ACH", "GABA", "GLUT", "DA", "SER", "OCT", "HIST", "UNKNOWN")

NEURON_SCHEMA = pa.schema(
    [
        pa.field("idx", pa.int32(), nullable=False),
        pa.field("root_id", pa.int64(), nullable=False),
        pa.field("name", pa.string()),
        pa.field("side", pa.string()),
        pa.field("flow", pa.string()),
        pa.field("super_class", pa.string()),
        pa.field("cell_class", pa.string()),
        pa.field("cell_sub_class", pa.string()),
        pa.field("cell_type", pa.string()),
        pa.field("hemibrain_type", pa.string()),
        pa.field("nt_type", pa.string()),
        pa.field("nt_confidence", pa.float32()),
        pa.field("pos_x", pa.float32()),
        pa.field("pos_y", pa.float32()),
        pa.field("pos_z", pa.float32()),
        pa.field("primary_neuropil", pa.string()),
        pa.field("input_synapses", pa.int64()),
        pa.field("output_synapses", pa.int64()),
    ]
)
"""One row per neuron. Positions are in nanometres in the dataset's native space."""

CONNECTION_SCHEMA = pa.schema(
    [
        pa.field("pre_root_id", pa.int64(), nullable=False),
        pa.field("post_root_id", pa.int64(), nullable=False),
        pa.field("neuropil", pa.string()),
        pa.field("syn_count", pa.int32(), nullable=False),
        pa.field("nt_type", pa.string()),
    ]
)
"""Source-resolution connections (per neuropil when the source provides it)."""

EDGE_SCHEMA = pa.schema(
    [
        pa.field("pre_idx", pa.int32(), nullable=False),
        pa.field("post_idx", pa.int32(), nullable=False),
        pa.field("syn_count", pa.int32(), nullable=False),
        pa.field("sign", pa.int8(), nullable=False),
    ]
)
"""Aggregated directed edges (one per ordered neuron pair), sorted by (pre_idx, post_idx).

``syn_count`` is the total number of reconstructed synapses from pre to post.
``sign`` is +1 (excitatory) or -1 (inhibitory) as assigned by the dataset's
sign policy (an assumption, recorded in the manifest), not a measured quantity.
"""

STRING_NEURON_COLUMNS = [f.name for f in NEURON_SCHEMA if pa.types.is_string(f.type)]

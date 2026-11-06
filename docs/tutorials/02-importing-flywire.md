# 2. Importing FlyWire data

## Open sources (no sign-in)

```bash
uv run flymind data sources          # what can be fetched, sizes, licences
uv run flymind data fetch flywire-783 # ~150 MB; checksummed; imports and validates
uv run flymind data info
```

This builds `data/processed/flywire_fafb_783/` (139,255 neurons, 15,091,983 connections,
54,492,922 synapses) and prints the validation report. Optional extras:

```bash
uv run flymind data fetch flywire-630   # the exact Shiu et al. v630 network (reproduction)
uv run flymind data fetch skeletons     # 5.4 GB neuron skeletons for the 3D explorer
```

## Codex files (sign-in required)

1. Sign in at <https://codex.flywire.ai/api/download> and accept the FlyWire terms.
2. Download, for version 783, e.g. `neurons`, `classification`, `consolidated_cell_types`,
   `connections`, `coordinates`, `names` into one folder (gzipped CSVs are fine).
3. Import (files are recognised by their header rows):

```bash
uv run flymind data import ~/Downloads/flywire_783 --connectivity codex
uv run flymind data validate flywire_fafb_783
```

You can mix the open bundle with Codex files in one folder; Codex annotations then take
precedence, and every file must reference only v783 neurons or the import is refused.

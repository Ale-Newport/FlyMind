# 3. Exploring a neuron

1. Choose **FlyWire FAFB v783** in the dataset selector (top right) and open
   **Brain Explorer** (`Alt+2`).
2. Search `DNa02` → click a result. The panel shows identifiers, annotations, the
   predicted transmitter (with its confidence; an inference, not a measurement), input
   and output partner counts and synapse totals.
3. With skeletons installed, the reconstructed morphology is drawn (LOD 1: roots, branch
   points, leaves and every 3rd node kept; counts are shown).
4. **Connectivity**: switch Outputs/Inputs, change the synapse threshold; inputs are
   highlighted cyan and outputs pink in 3D. Click a partner to navigate to it.
5. **Trace pathway**: enter source and target IDs, e.g. sugar GRN `720575940624963786`
   → MN9 `720575940660219265`, to get the shortest directed path with ≥5 synapses/hop.
6. **Export subgraph CSV** downloads the 1-hop subgraph with synapse counts and signs.

Proximity is not connectivity: two neighbouring points are connected only if listed as
partners.

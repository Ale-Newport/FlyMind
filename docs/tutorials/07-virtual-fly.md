# 7. Running the Virtual Fly

1. **Virtual Fly** → arena *Food*, controller *Baseline*, *Create fly session* (builds the
   MuJoCo model, ~1 s), *Start*. Adjust forward drive and turn live; the fly is the
   official NeuroMechFly body, its pose comes from MuJoCo.
2. Switch to *Neural (connectome)*: the bridge maps odour at the antennae to ORN input
   and descending-neuron rates to the walking command (see
   [the interface](../scientific/neural-body-interface.md)). The panel lists every input
   and readout rate, and which parts are connectome, model, controller and physics.
3. *Save recording* stores the trajectory, joint angles, poses and spikes under
   `experiments/fly_<id>/`; *Recorded sessions → Replay* plays it back without the backend
   simulating.

Headless: `uv run flymind fly run --arena food --controller neural --dataset flywire_fafb_783 --duration-s 3`.

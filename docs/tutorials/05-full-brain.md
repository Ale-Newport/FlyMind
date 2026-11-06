# 5. Running a full-brain simulation

Full-brain mode uses the entire imported graph (no substitute network). If the dataset is
missing the UI says so and shows the install command.

1. Dataset **FlyWire FAFB v783**, mode **full** → *Create session* (139,255 neurons).
2. Add a stimulus (e.g. `sugar_grn_shiu`, 200 Hz, stop blank = continuous) → *Start*.
3. The session panel shows simulated time, wall time and the measured sim/wall ratio
   (≈0.44× on an M2 Max; it is not real time).
4. In **Brain Explorer**, colour by **Simulated activity** to see active neurons; untick
   *Live* and move the window sliders to inspect earlier periods.

Memory: the v783 graph is memory-mapped (~250 MB); a session adds ~10 MB plus spikes.

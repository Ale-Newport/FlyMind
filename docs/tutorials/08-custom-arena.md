# 8. Creating a custom arena

Choose **Experimental arena**, open *Edit objects & conditions*, and add odour sources
(attractive/aversive/neutral), obstacles (collidable boxes), light pillars (emissive,
visible to the compound eyes) and food patches; set coordinates in mm (the fly starts at
the origin facing +x) and ambient light. The configuration is sent with the session and
saved in its record. Programmatic equivalent:

```python
from flymind.embodiment.arena import ArenaConfig, OdorSource, Obstacle
arena = ArenaConfig(kind="experimental", name="T-maze-ish",
                    odor_sources=[OdorSource(x_mm=20, y_mm=10, valence="attractive")],
                    obstacles=[Obstacle(x_mm=10, y_mm=0, half_x_mm=0.5, half_y_mm=4)])
```

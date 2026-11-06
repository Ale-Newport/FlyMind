# Flight model

FlyGym 2.x (NeuroMechFly v2) is a **walking** model: its wings are rigid meshes with no joints.
Flight in FlyMind is therefore a separate, deliberately small component
(`src/flymind/embodiment/flight.py`), labelled everywhere as a **FlyMind model**, not a FlyGym or
connectome result.

## What is modelled

| Part | Origin | Evidence category |
|---|---|---|
| Mass (1.02 mg), centre of mass, inertia, wing length (2.40 mm), wing area (2.0 mm²), chord profile, hinge positions | measured from the NeuroMechFly v2 meshes and inertial data | published model |
| Wing aerodynamics: blade-element model with translational lift and drag, `C_L = 0.225 + 1.58 sin(2.13α − 7.2°)`, `C_D = 1.92 − 1.55 cos(2.04α − 9.83°)` | Dickinson, Lehmann & Sane 1999 (dynamically scaled *Drosophila* wing) | published coefficients, FlyMind implementation |
| Wingbeat-averaged forces (16 phase samples × 6 span stations per wing), 200 Hz wingbeat, sinusoidal stroke, smooth pitch reversal | FlyMind assumption | assumption |
| Body integrated as a 6-DoF rigid body at 1 ms | FlyMind | simulation output |
| Flight controller: velocity → thrust vector → tilt-prioritised attitude → wing-kinematics allocation (damped least squares) | FlyMind engineering | **external algorithm, not the connectome** |
| Wing actuators: stroke amplitude, stroke-centre offset and pitch of each wing, with a 5 ms lag | FlyMind assumption | assumption |
| Take-off, landing, leg folding with height | FlyMind (legs follow an inverse-kinematics posture solved on the NeuroMechFly model) | assumption |

The relative air velocity of every wing section includes the body velocity and rotation, so
flapping-counter-torque damping and speed-dependent drag emerge without extra terms.

## What the model reproduces (unit-tested)

* Hover needs a stroke amplitude of ≈ 140°, inside the 140–150° reported for *D. melanogaster*
  hovering; the body settles nose-up at ≈ 38°.
* Forward flight reaches the commanded speed with no roll; the body pitches down as speed rises.
* A 90° body saccade completes in under 150 ms (peak yaw rate ≈ 1,400°/s) with banking that recovers,
  comparable to free-flight saccades of flies.
* Left and right turns are mirror images; landing is a soft touch-down; obstacles stop the fly.

## What is not modelled

Rotational circulation, added mass, wake capture, wing–body interference, ground effect, wind and
turbulence, within-stroke force oscillations (the body filters them), the haltere feedback loop, and
muscle dynamics. Wing motion is drawn in slow motion (about 40× slower than the real 200 Hz stroke)
because the real stroke would alias at the stream rate.

Walking and flying run on different physics (FlyGym/MuJoCo vs. this model). The body hand-over at
take-off and landing copies position and heading; the walking controller restarts at landing.

## Behaviour layers

* `LocomotionController` (`behavior.py`): `ground → takeoff → flight → landing → ground`.
* Manual and neural controllers send an *intent* (forward drive, turn, walk or fly). With the neural
  controller only the forward and turning commands come from the connectome readout; flapping,
  hover stabilisation and altitude hold are the flight controller (the session record carries a
  `scripted_flight_warning`).
* **Autonomous** controller: a scripted *demonstration* policy of documented fly behaviours (walking
  bouts and pauses, take-off, straight flight segments with saccades, odour tracking by antennal
  differences and temporal change, landing on food, feeding, obstacle and aversive-odour avoidance).
  It is not a model of the connectome.

## References

* Dickinson, M. H., Lehmann, F.-O. & Sane, S. P. (1999) Wing rotation and the aerodynamic basis of
  insect flight. *Science* 284, 1954–1960.
* Fry, S. N., Sayaman, R. & Dickinson, M. H. (2005) The aerodynamics of hovering flight in
  *Drosophila*. *J. Exp. Biol.* 208, 2303–2318.
* Wang-Chen, S. et al. (2024) NeuroMechFly 2.0. *Nature Methods* 21, 2353.

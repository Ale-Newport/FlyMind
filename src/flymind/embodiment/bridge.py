"""Neural <-> body interface: World -> Sensors -> Neural inputs, Neural outputs -> Motor commands.

Everything that crosses the boundary between the simulated brain and the simulated
body is declared here, with its provenance:

* **Sensory encoding** (``SensoryChannel``): a scalar sensor value is turned into a
  Poisson firing rate imposed on a named group of sensory neurons
  (rate = clip(gain * (value - baseline), 0, max_rate)). The choice of neurons comes
  from the literature (cited per group); the linear rate code and its gain are
  FlyMind modelling assumptions.
* **Motor readout** (``MotorReadout``): exponentially smoothed population firing
  rates of named descending-neuron groups are mapped to the two-value descending
  command of FlyGym's ``HybridTurningController`` (a CPG + sensory-feedback walking
  controller; Wang-Chen et al. 2024). That controller, not the connectome, generates
  leg kinematics: the FAFB connectome contains no ventral nerve cord, so leg motor
  circuits are not part of the neural model.

No tonic or scripted drive is added by default: if the selected neurons are silent
the descending command is zero and the fly does not walk.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

SensorKey = Literal[
    "odor_attractive_left",
    "odor_attractive_right",
    "odor_aversive_left",
    "odor_aversive_right",
    "luminance_left",
    "luminance_right",
    "contact_left",
    "contact_right",
    "on_food",
]
MotorRole = Literal[
    "forward_left",
    "forward_right",
    "turn_left",
    "turn_right",
    "backward_left",
    "backward_right",
    "monitor",
]


class SensoryChannel(BaseModel):
    sensor: SensorKey
    group: str = Field(description="neuron group name in the dataset's group file")
    gain_hz: float = Field(200.0, ge=0, le=5000, description="Hz per sensor unit")
    baseline: float = Field(0.0, description="sensor value giving 0 Hz")
    max_rate_hz: float = Field(200.0, ge=0, le=1000)
    note: str = ""


class MotorReadout(BaseModel):
    role: MotorRole
    group: str
    note: str = ""


class BridgeConfig(BaseModel):
    name: str
    dataset_ids: list[str]
    description: str
    evidence: Literal["published", "simulation_output", "hypothesis", "demonstration"]
    sensory: list[SensoryChannel]
    motor: list[MotorReadout]
    tau_ms: float = Field(50.0, gt=0, le=2000, description="readout smoothing time constant")
    r_half_hz: float = Field(20.0, gt=0, le=1000, description="rate giving half-maximal drive")
    max_amplitude: float = Field(1.2, gt=0, le=2.0)
    turn_gain: float = Field(0.8, ge=0, le=2.0)
    tonic_forward: float = Field(
        0.0, ge=0, le=1.2, description="scripted forward drive (0 = none; reported if > 0)"
    )
    interval_ms: float = Field(1.0, gt=0, le=50, description="sensor/readout update interval")


BRIDGE_PRESETS: dict[str, BridgeConfig] = {
    "synthetic_demo": BridgeConfig(
        name="synthetic_demo",
        dataset_ids=["synthetic_demo_v1"],
        description="Synthetic network whose sensory->descending pathways were wired by hand to "
        "demonstrate the closed loop. Behaviour is designed, not emergent.",
        evidence="demonstration",
        sensory=[
            SensoryChannel(sensor="odor_attractive_left", group="orn_attr_l", gain_hz=250),
            SensoryChannel(sensor="odor_attractive_right", group="orn_attr_r", gain_hz=250),
            SensoryChannel(sensor="odor_aversive_left", group="orn_avers_l", gain_hz=250),
            SensoryChannel(sensor="odor_aversive_right", group="orn_avers_r", gain_hz=250),
            SensoryChannel(sensor="luminance_left", group="vis_l", gain_hz=400, baseline=0.25),
            SensoryChannel(sensor="luminance_right", group="vis_r", gain_hz=400, baseline=0.25),
            SensoryChannel(sensor="contact_left", group="mech_l", gain_hz=300),
            SensoryChannel(sensor="contact_right", group="mech_r", gain_hz=300),
            SensoryChannel(sensor="on_food", group="grn_sugar", gain_hz=150),
        ],
        motor=[
            MotorReadout(role="forward_left", group="dn_fwd_l"),
            MotorReadout(role="forward_right", group="dn_fwd_r"),
            MotorReadout(role="turn_left", group="dn_turn_l"),
            MotorReadout(role="turn_right", group="dn_turn_r"),
            MotorReadout(role="backward_left", group="dn_back_l"),
            MotorReadout(role="backward_right", group="dn_back_r"),
            MotorReadout(role="monitor", group="mn_feed"),
        ],
    ),
    "flywire_literature": BridgeConfig(
        name="flywire_literature",
        dataset_ids=["flywire_fafb_783"],
        description="Literature-defined sensory entry points and descending neurons in FlyWire "
        "v783. Whether the connectome model routes sensory input to these "
        "descending neurons is an open question the experiment tests.",
        evidence="hypothesis",
        sensory=[
            SensoryChannel(
                sensor="odor_attractive_left",
                group="orn_dm1_left",
                gain_hz=200,
                note="Or42b/DM1 ORNs; vinegar attraction (Semmelhack & Wang 2009)",
            ),
            SensoryChannel(sensor="odor_attractive_right", group="orn_dm1_right", gain_hz=200),
            SensoryChannel(
                sensor="odor_aversive_left",
                group="orn_da2_left",
                gain_hz=200,
                note="Or56a/DA2 ORNs; geosmin aversion (Stensmyr et al. 2012)",
            ),
            SensoryChannel(sensor="odor_aversive_right", group="orn_da2_right", gain_hz=200),
            SensoryChannel(
                sensor="luminance_left",
                group="r7_left",
                gain_hz=100,
                baseline=0.1,
                note="eye-averaged luminance; columns not mapped individually",
            ),
            SensoryChannel(sensor="luminance_right", group="r7_right", gain_hz=100, baseline=0.1),
            SensoryChannel(
                sensor="on_food",
                group="sugar_grn_shiu",
                gain_hz=150,
                note="sugar GRNs (Shiu et al. 2024) when the body is on a food patch",
            ),
        ],
        motor=[
            MotorReadout(
                role="forward_left",
                group="p9_left",
                note="P9/DNp09 drives forward walking (Bidaye et al. 2020)",
            ),
            MotorReadout(role="forward_right", group="p9_right"),
            MotorReadout(
                role="turn_left",
                group="dna02_left",
                note="DNa02 predicts ipsilateral steering (Rayshubskiy et al. 2025)",
            ),
            MotorReadout(role="turn_right", group="dna02_right"),
            MotorReadout(
                role="backward_left",
                group="mdn_left",
                note="MDN drives backward walking (Bidaye et al. 2014)",
            ),
            MotorReadout(role="backward_right", group="mdn_right"),
            MotorReadout(
                role="monitor",
                group="mn9",
                note="MN9 proboscis motor neurons (feeding readout only)",
            ),
        ],
    ),
}


class SensoryEncoder:
    """Turns sensor values into Poisson input events for the brain engine."""

    def __init__(
        self,
        cfg: BridgeConfig,
        groups_local: dict[str, np.ndarray],
        weight: float,
        dt_ms: float,
        seed: int,
    ):
        self.cfg = cfg
        self.groups = groups_local
        self.weight = weight
        self.dt_ms = dt_ms
        self.rng = np.random.default_rng(np.random.SeedSequence([seed, 0xB1D6E]))
        self.last_rates: dict[str, float] = {}

    def rates(self, sensors: dict[str, float]) -> dict[str, float]:
        out = {}
        for ch in self.cfg.sensory:
            v = float(sensors.get(ch.sensor, 0.0))
            out[f"{ch.sensor}->{ch.group}"] = float(
                np.clip(ch.gain_hz * (v - ch.baseline), 0.0, ch.max_rate_hz)
            )
        self.last_rates = out
        return out

    def events(self, sensors: dict[str, float], t0_step: int, n_steps: int):
        rates = self.rates(sensors)
        steps_l, idx_l = [], []
        for ch in self.cfg.sensory:
            members = self.groups.get(ch.group)
            r = rates[f"{ch.sensor}->{ch.group}"]
            if members is None or len(members) == 0 or r <= 0:
                continue
            p = r * self.dt_ms * 1e-3
            hits = self.rng.random((n_steps, len(members))) < p
            si, mi = np.nonzero(hits)
            steps_l.append(si.astype(np.int64) + t0_step)
            idx_l.append(members[mi])
        if not steps_l:
            z = np.zeros(0, dtype=np.int64)
            return z, z, np.zeros(0)
        steps = np.concatenate(steps_l)
        idx = np.concatenate(idx_l).astype(np.int64)
        order = np.lexsort((idx, steps))
        return steps[order], idx[order], np.full(len(steps), self.weight)


class MotorDecoder:
    """Smoothed population rates of readout groups -> descending command [left, right]."""

    def __init__(self, cfg: BridgeConfig, groups_local: dict[str, np.ndarray]):
        self.cfg = cfg
        self.groups = groups_local
        self.rate: dict[str, float] = {m.group: 0.0 for m in cfg.motor}

    def update(
        self, spike_local: np.ndarray, interval_ms: float, silenced: np.ndarray | None = None
    ) -> dict[str, float]:
        """``silenced``: engine-local idx whose synaptic output is blocked or clamped. Their
        spikes do not reach the (implicit) ventral nerve cord either, so they are excluded
        from the descending readout, as genetic silencing of a DN would remove its effect."""
        alpha = 1.0 - np.exp(-interval_ms / self.cfg.tau_ms)
        if silenced is not None and len(silenced):
            spike_local = spike_local[~np.isin(spike_local, silenced)]
        for m in self.cfg.motor:
            members = self.groups.get(m.group)
            if members is None or len(members) == 0:
                inst = 0.0
            else:
                inst = (
                    float(np.isin(spike_local, members).sum())
                    / len(members)
                    / (interval_ms / 1000.0)
                )
            self.rate[m.group] += alpha * (inst - self.rate[m.group])
        return dict(self.rate)

    def _sat(self, role: str) -> float:
        groups = [m.group for m in self.cfg.motor if m.role == role]
        if not groups:
            return 0.0
        r = float(np.mean([self.rate[g] for g in groups]))
        return r / (r + self.cfg.r_half_hz)

    def descending(self) -> tuple[np.ndarray, dict[str, float]]:
        c = self.cfg
        fwd = 0.5 * (self._sat("forward_left") + self._sat("forward_right"))
        back = 0.5 * (self._sat("backward_left") + self._sat("backward_right"))
        turn = self._sat("turn_left") - self._sat("turn_right")  # >0: steer left
        amp = c.max_amplitude * (fwd - back) + c.tonic_forward
        # Left-turn: shorten left strides, lengthen right strides (HybridTurningController
        # turns away from the side with larger amplitude).
        d_left = np.clip(
            amp - c.turn_gain * c.max_amplitude * turn, -c.max_amplitude, c.max_amplitude
        )
        d_right = np.clip(
            amp + c.turn_gain * c.max_amplitude * turn, -c.max_amplitude, c.max_amplitude
        )
        return np.array([d_left, d_right]), {
            "forward": fwd,
            "backward": back,
            "turn": turn,
            "amplitude": amp,
        }

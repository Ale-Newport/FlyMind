"""Leaky integrate-and-fire parameters with per-parameter provenance.

Model (Shiu et al. 2024, Nature 634:210-219, "A Drosophila computational brain model
reveals sensorimotor processing"; reference code github.com/philshiu/Drosophila_brain_model):

    dv/dt = (v_0 - v + g) / tau_m          (unless refractory)
    dg/dt = -g / tau_syn                   (unless refractory, see hold_g_during_refractory)
    spike when v > v_th  ->  v := v_reset, g := 0, refractory for t_ref
    presynaptic spike    ->  g_post += w   after a fixed delay t_dly
    w = sign(pre transmitter) * synapse_count * w_syn
    Poisson input spike  ->  v += f_poi * w_syn (68.75 mV), stimulated neurons have t_ref = 0

FlyMind extension (not in the reference model): a constant drive term ``I`` (in mV,
i.e. R_m * I_inj) used for "current injection" experiments:

    dv/dt = (v_0 + I - v + g) / tau_m
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

ParamStatus = Literal[
    "reference_model", "reference_model_estimate", "flymind_choice", "exploratory"
]


class ParamInfo(BaseModel):
    units: str
    description: str
    source: str
    status: ParamStatus


class LIFParams(BaseModel):
    """Model parameters. Defaults reproduce the Shiu et al. (2024) reference model."""

    v_rest_mV: float = Field(-52.0, description="resting potential v_0")
    v_reset_mV: float = Field(-52.0, description="reset potential after a spike")
    v_threshold_mV: float = Field(-45.0, description="spike threshold")
    tau_m_ms: float = Field(20.0, gt=0, description="membrane time constant")
    tau_syn_ms: float = Field(5.0, gt=0, description="synaptic time constant")
    t_refractory_ms: float = Field(2.2, ge=0, description="absolute refractory period")
    delay_ms: float = Field(1.8, ge=0, description="synaptic transmission delay")
    w_syn_mV: float = Field(0.275, description="weight per synapse")
    poisson_weight_factor: float = Field(
        250.0, description="Poisson input weight = factor * w_syn (f_poi in reference code)"
    )
    dt_ms: float = Field(0.1, gt=0, le=1.0, description="integration time step")
    hold_g_during_refractory: bool = Field(
        True, description="reference model marks both v and g '(unless refractory)'"
    )
    reset_g: bool = Field(True, description="reference reset is 'v = v_rst; g = 0 mV'")
    drop_input_during_refractory: bool = Field(
        True, description="Brian2 conditional write: input to refractory neurons is discarded"
    )
    stimulated_refractory_zero: bool = Field(
        True, description="reference model sets rfc = 0 for Poisson-stimulated neurons"
    )
    precision: Literal["float64", "float32"] = "float64"

    # ----------------------------------------------------------- derived steps
    @property
    def delay_steps(self) -> int:
        return int(round(self.delay_ms / self.dt_ms))

    @property
    def refractory_steps(self) -> int:
        # Brian2: timestep(refractory, dt) = floor(refractory/dt + 1e-3)
        return int(math.floor(self.t_refractory_ms / self.dt_ms + 1e-3))

    def propagators(self) -> tuple[float, float, float]:
        """Exact one-step propagators (a_vv, a_vg, a_gg) of the linear subthreshold system."""
        dt, tm, ts = self.dt_ms, self.tau_m_ms, self.tau_syn_ms
        a_vv = math.exp(-dt / tm)
        a_gg = math.exp(-dt / ts)
        if math.isclose(tm, ts):
            a_vg = (dt / tm) * math.exp(-dt / tm)
        else:
            a_vg = ts / (ts - tm) * (math.exp(-dt / ts) - math.exp(-dt / tm))
        return a_vv, a_vg, a_gg


PARAMETER_INFO: dict[str, ParamInfo] = {
    "v_rest_mV": ParamInfo(
        units="mV",
        description="resting membrane potential",
        source="Shiu et al. 2024 (reference code v_0)",
        status="reference_model",
    ),
    "v_reset_mV": ParamInfo(
        units="mV",
        description="post-spike reset potential",
        source="Shiu et al. 2024 (reference code v_rst)",
        status="reference_model",
    ),
    "v_threshold_mV": ParamInfo(
        units="mV",
        description="spike threshold",
        source="Shiu et al. 2024 (reference code v_th)",
        status="reference_model",
    ),
    "tau_m_ms": ParamInfo(
        units="ms",
        description="membrane time constant",
        source="Shiu et al. 2024 (t_mbr = R*C)",
        status="reference_model",
    ),
    "tau_syn_ms": ParamInfo(
        units="ms",
        description="synaptic decay time constant",
        source="Shiu et al. 2024 (tau)",
        status="reference_model",
    ),
    "t_refractory_ms": ParamInfo(
        units="ms",
        description="refractory period",
        source="Shiu et al. 2024 (t_rfc)",
        status="reference_model",
    ),
    "delay_ms": ParamInfo(
        units="ms",
        description="uniform synaptic delay",
        source="Shiu et al. 2024 (t_dly)",
        status="reference_model",
    ),
    "w_syn_mV": ParamInfo(
        units="mV",
        description="weight per reconstructed synapse",
        source="Shiu et al. 2024 (w_syn; tuned, not measured)",
        status="reference_model_estimate",
    ),
    "poisson_weight_factor": ParamInfo(
        units="dimensionless",
        description="scales Poisson input so each input spike is strong",
        source="Shiu et al. 2024 (f_poi)",
        status="reference_model_estimate",
    ),
    "dt_ms": ParamInfo(
        units="ms",
        description="integration step",
        source="Shiu et al. 2024 (Brian2 default 0.1 ms)",
        status="reference_model",
    ),
    "hold_g_during_refractory": ParamInfo(
        units="bool",
        description="freeze g while refractory",
        source="Brian2 '(unless refractory)' flag in the reference equations",
        status="reference_model",
    ),
    "drop_input_during_refractory": ParamInfo(
        units="bool",
        description="discard synaptic/Poisson input arriving while refractory",
        source="Brian2 semantics of '(unless refractory)' (conditional write) in the reference "
        "model",
        status="reference_model",
    ),
    "reset_g": ParamInfo(
        units="bool",
        description="zero g at spike reset",
        source="Shiu et al. 2024 reference code eq_rst",
        status="reference_model",
    ),
    "stimulated_refractory_zero": ParamInfo(
        units="bool",
        description="Poisson/pulse-stimulated neurons have no refractory period",
        source="Shiu et al. 2024 reference code poi(): neu[i].rfc = 0 ms",
        status="reference_model",
    ),
    "precision": ParamInfo(
        units="-",
        description="floating-point precision of state",
        source="FlyMind",
        status="flymind_choice",
    ),
}

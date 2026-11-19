"""Reproducible experiment specification.

An experiment is a set of *conditions* (e.g. intact vs lesioned) run for
``n_trials`` trials each, on one dataset, with fixed parameters and seeds. Neurons
are addressed by :class:`NeuronSelector` (root IDs / annotations), never by
storage indices, so a spec is portable across machines for the same dataset
version. The spec, the resolved neuron IDs and all provenance are saved with the
results.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from flymind.brain.params import LIFParams
from flymind.brain.session import InterventionSpec, NetworkConfig, StimulusSpec
from flymind.connectome.selectors import NeuronSelector
from flymind.embodiment.session import FlySessionConfig


class Readout(BaseModel):
    name: str
    selector: NeuronSelector


class Condition(BaseModel):
    name: str
    stimuli: list[StimulusSpec] = Field(default_factory=list, max_length=256)
    interventions: list[InterventionSpec] = Field(default_factory=list, max_length=256)
    params: dict[str, float | bool | str] = Field(
        default_factory=dict,
        max_length=32,
        description="overrides of LIFParams fields for this condition",
    )


class ExpectedResult(BaseModel):
    """A published or reference value the experiment attempts to reproduce."""

    readout: str
    condition: str
    value_hz: float
    tolerance_hz: float
    source: str
    note: str = ""


class ExperimentSpec(BaseModel):
    name: str
    template: str = "custom"
    description: str = ""
    dataset_id: str
    network: NetworkConfig = NetworkConfig()
    params: LIFParams = LIFParams()
    conditions: list[Condition] = Field(min_length=1, max_length=24)
    readouts: list[Readout] = Field(default_factory=list, max_length=64)
    duration_ms: float = Field(1000.0, gt=0, le=60_000)
    n_trials: int = Field(1, ge=1, le=100)
    seed: int = Field(0, ge=0, le=2**31 - 1)
    backend: Literal["numba", "numpy"] = "numba"
    bin_ms: float = Field(10.0, ge=0.1, le=1000)
    embodiment: FlySessionConfig | None = None
    expected: list[ExpectedResult] = Field(default_factory=list, max_length=64)
    evidence: Literal[
        "published", "reproduced", "simulation_output", "hypothesis", "demonstration"
    ] = "simulation_output"
    assumptions: list[str] = Field(default_factory=list, max_length=64)

    def condition_params(self, cond: Condition) -> LIFParams:
        """``params`` with the condition's overrides applied and fully validated."""
        known = type(self.params).model_fields
        overrides = {k: v for k, v in cond.params.items() if k in known}
        return type(self.params).model_validate({**self.params.model_dump(), **overrides})

    @model_validator(mode="after")
    def _check_condition_params(self) -> ExperimentSpec:
        # Overrides are validated here so an invalid dt_ms or a wrongly typed value is
        # rejected when the spec is submitted, not deep inside a worker thread.
        for cond in self.conditions:
            self.condition_params(cond)
        return self

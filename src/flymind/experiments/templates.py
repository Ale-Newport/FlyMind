"""Experiment templates (the eight required scientific experiments + embodied ones).

Each template builds an :class:`ExperimentSpec` for a given dataset. Templates are
only offered for datasets on which their neuron groups exist.
"""

from __future__ import annotations

from collections.abc import Callable

from flymind.brain.params import LIFParams
from flymind.brain.session import InterventionSpec, NetworkConfig, StimulusSpec
from flymind.connectome.selectors import NeuronSelector as S
from flymind.embodiment.arena import arena_preset
from flymind.embodiment.session import BaselineCommand, FlySessionConfig
from flymind.experiments.spec import Condition, ExpectedResult, ExperimentSpec, Readout

FIXTURE = "synthetic_demo_v1"
FW783 = "flywire_fafb_783"
FW630 = "flywire_fafb_630_shiu"
SHIU_REF = (
    "Shiu et al. 2024 reference results (results/example/sugarR*.parquet in "
    "philshiu/Drosophila_brain_model @91bdd1e7; mean of 30 trials, v630)"
)
LIF_ASSUMPTIONS = [
    "Synaptic weight = predicted-transmitter sign x synapse count x w_syn "
    "(w_syn tuned, not measured).",
    "Transmitter signs: GABA and glutamate inhibitory, all others excitatory.",
    "Point neurons; no dendritic compartments, gap junctions, neuromodulation or plasticity.",
    "Uniform 1.8 ms synaptic delay; no spontaneous activity "
    "(only stimulated inputs drive the network).",
]


def _sel(group: str) -> S:
    return S(group=group)


def single_neuron_activation(ds: str) -> ExperimentSpec:
    if ds == FIXTURE:
        stim, reads = _sel("chain_a"), ["chain_a", "chain_b", "chain_c"]
    else:
        stim = S(root_ids=[720575940624963786])  # one sugar GRN (Shiu et al. list)
        reads = ["mn9"] if ds == FW783 else ["mn9_shiu"]
    return ExperimentSpec(
        name="Single-neuron activation",
        template="single_neuron_activation",
        dataset_id=ds,
        description="Poisson activation of one neuron; which downstream neurons respond? "
        "Approximates optogenetic activation of a single identified cell.",
        conditions=[
            Condition(
                name="stimulated",
                stimuli=[
                    StimulusSpec(
                        selector=stim, rate_hz=150, start_ms=0, stop_ms=800, label="single neuron"
                    )
                ],
            )
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=1000,
        n_trials=5,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def population_stimulation(ds: str) -> ExperimentSpec:
    if ds == FIXTURE:
        grp, reads = "grn_sugar", ["mn_feed", "sez_int"]
    else:
        grp, reads = "sugar_grn_shiu", (["mn9"] if ds == FW783 else ["mn9_shiu"])
    return ExperimentSpec(
        name="Population stimulation frequency sweep",
        template="population_stimulation",
        dataset_id=ds,
        description="Sugar-sensing GRNs driven at increasing Poisson rates (cf. Shiu et al. 2024 "
        "Fig. 1d); readout of the feeding motor neuron MN9.",
        conditions=[
            Condition(
                name=f"{hz} Hz",
                stimuli=[StimulusSpec(selector=_sel(grp), rate_hz=hz, label="sugar GRNs")],
            )
            for hz in (25, 50, 100, 150, 200)
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=1000,
        n_trials=5,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def silencing(ds: str) -> ExperimentSpec:
    if ds == FIXTURE:
        stim, sil, reads = "orn_attr_l", "pn_attr_l", ["lhn_attr_l", "dn_turn_l"]
        sil_sel = _sel(sil)
    else:
        stim = "sugar_grn_shiu"
        sil_sel = S(root_ids=[720575940617937543, 720575940621754367])
        reads = ["mn9"] if ds == FW783 else ["mn9_shiu"]
    return ExperimentSpec(
        name="Silencing intervention",
        template="silencing",
        dataset_id=ds,
        description="Same stimulation with and without silencing a neuron group (synaptic output "
        "blocked, as in the reference model; approximates tetanus-toxin silencing).",
        conditions=[
            Condition(name="intact", stimuli=[StimulusSpec(selector=_sel(stim), rate_hz=100)]),
            Condition(
                name="silenced",
                stimuli=[StimulusSpec(selector=_sel(stim), rate_hz=100)],
                interventions=[
                    InterventionSpec(
                        kind="silence", selector=sil_sel, mode="block_output", label="silenced"
                    )
                ],
            ),
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=1000,
        n_trials=10,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def propagation(ds: str) -> ExperimentSpec:
    if ds == FIXTURE:
        stim, reads = (
            "orn_attr_l",
            ["orn_attr_l", "pn_attr_l", "lhn_attr_l", "dn_turn_l", "dn_fwd_l"],
        )
    else:
        stim, reads = "orn_dm1_left", ["orn_dm1_left", "p9_left", "dna02_left", "dna02_right"]
    return ExperimentSpec(
        name="Propagation across regions",
        template="propagation",
        dataset_id=ds,
        description="A 200 ms olfactory receptor neuron stimulus; activity spreads across "
        "neuropils "
        "(see regions.csv and timecourse.csv).",
        conditions=[
            Condition(
                name="odor pulse",
                stimuli=[
                    StimulusSpec(
                        selector=_sel(stim),
                        rate_hz=150,
                        start_ms=100,
                        stop_ms=300,
                        label="ORN pulse",
                    )
                ],
            )
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=500,
        n_trials=5,
        bin_ms=5,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def sensory_circuit_reproduction(ds: str) -> ExperimentSpec:
    if ds == FW630:
        return ExperimentSpec(
            name="Sugar GRN -> MN9 (reproduction of Shiu et al. 2024)",
            template="sensory_circuit",
            dataset_id=ds,
            description="Exact v630 network and neuron IDs of the reference example: 21 sugar GRNs "
            "Poisson-driven at 200 Hz and 100 Hz, 30 trials of 1 s; MN9 firing rate "
            "compared with the reference implementation's committed results.",
            conditions=[
                Condition(
                    name="200 Hz",
                    stimuli=[
                        StimulusSpec(selector=_sel("sugar_grn_shiu"), rate_hz=200, label="sugarR")
                    ],
                ),
                Condition(
                    name="100 Hz",
                    stimuli=[
                        StimulusSpec(selector=_sel("sugar_grn_shiu"), rate_hz=100, label="sugarR")
                    ],
                ),
            ],
            readouts=[Readout(name="mn9_shiu", selector=_sel("mn9_shiu"))],
            duration_ms=1000,
            n_trials=30,
            expected=[
                ExpectedResult(
                    readout="mn9_shiu",
                    condition="200 Hz",
                    value_hz=93.3,
                    tolerance_hz=3.0,
                    source=SHIU_REF,
                    note="reference SD across trials 3.2 Hz; tolerance ~5 standard errors",
                ),
                ExpectedResult(
                    readout="mn9_shiu",
                    condition="100 Hz",
                    value_hz=67.0,
                    tolerance_hz=4.0,
                    source=SHIU_REF,
                    note="reference SD across trials 6.6 Hz",
                ),
            ],
            evidence="published",
            assumptions=LIF_ASSUMPTIONS,
        )
    if ds == FIXTURE:
        grp, rd = "grn_sugar", "mn_feed"
    else:
        grp, rd = "sugar_grn_shiu", "mn9"
    return ExperimentSpec(
        name="Sugar GRN -> feeding motor neuron",
        template="sensory_circuit",
        dataset_id=ds,
        description="Gustatory activation of a documented feeding circuit (Shiu et al. 2024) on "
        + (
            "the synthetic network."
            if ds == FIXTURE
            else "FlyWire v783 (exploratory: the published values were obtained on v630)."
        ),
        conditions=[
            Condition(name="200 Hz", stimuli=[StimulusSpec(selector=_sel(grp), rate_hz=200)])
        ],
        readouts=[Readout(name=rd, selector=_sel(rd))],
        duration_ms=1000,
        n_trials=10,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def parameter_comparison(ds: str) -> ExperimentSpec:
    grp, rd = (
        ("grn_sugar", "mn_feed")
        if ds == FIXTURE
        else ("sugar_grn_shiu", "mn9" if ds == FW783 else "mn9_shiu")
    )
    return ExperimentSpec(
        name="Parameter comparison: weight per synapse",
        template="parameter_comparison",
        dataset_id=ds,
        description="w_syn is a free parameter of the reference model; this sweep shows how the "
        "readout depends on it.",
        conditions=[
            Condition(
                name=f"w_syn={w}",
                params={"w_syn_mV": w},
                stimuli=[StimulusSpec(selector=_sel(grp), rate_hz=150)],
            )
            for w in (0.2, 0.275, 0.35)
        ],
        readouts=[Readout(name=rd, selector=_sel(rd))],
        duration_ms=1000,
        n_trials=5,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def intact_vs_lesioned(ds: str) -> ExperimentSpec:
    if ds == FIXTURE:
        stim, pre, post, reads = "orn_attr_l", "lhn_attr_l", "dn_turn_l", ["dn_turn_l", "dn_fwd_l"]
        post_sel = _sel(post)
    else:
        stim, pre, reads = (
            "sugar_grn_shiu",
            "sugar_grn_shiu",
            (["mn9"] if ds == FW783 else ["mn9_shiu"]),
        )
        post_sel = None
    lesions = [("intact", None), ("50% weakened", 0.5), ("lesioned", 0.0)]
    return ExperimentSpec(
        name="Intact vs lesioned connections",
        template="intact_vs_lesioned",
        dataset_id=ds,
        description="Reversible scaling of selected connections (factor 0 = connection lesion). "
        "The stored connectome is never modified.",
        conditions=[
            Condition(
                name=name,
                stimuli=[StimulusSpec(selector=_sel(stim), rate_hz=150)],
                interventions=[]
                if f is None
                else [
                    InterventionSpec(
                        kind="synaptic_scaling",
                        selector=_sel(pre),
                        post_selector=post_sel,
                        factor=f,
                        label=name,
                    )
                ],
            )
            for name, f in lesions
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=1000,
        n_trials=5,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def repeated_stimuli(ds: str) -> ExperimentSpec:
    grp, reads = (
        ("orn_attr_l", ["pn_attr_l", "dn_turn_l"])
        if ds == FIXTURE
        else ("sugar_grn_shiu", ["mn9"] if ds == FW783 else ["mn9_shiu"])
    )
    return ExperimentSpec(
        name="Repeated stimuli",
        template="repeated_stimuli",
        dataset_id=ds,
        description="Five 100 ms pulses every 300 ms. The model has no plasticity or adaptation, "
        "so identical responses are expected; deviations would indicate state carry-over.",
        conditions=[
            Condition(
                name="5 pulses",
                stimuli=[
                    StimulusSpec(
                        selector=_sel(grp),
                        rate_hz=200,
                        start_ms=50,
                        stop_ms=150,
                        repeats=5,
                        interval_ms=300,
                        label="pulse",
                    )
                ],
            )
        ],
        readouts=[Readout(name=r, selector=_sel(r)) for r in reads],
        duration_ms=1600,
        n_trials=5,
        bin_ms=10,
        assumptions=LIF_ASSUMPTIONS,
        evidence="demonstration" if ds == FIXTURE else "simulation_output",
    )


def embodied_controller_comparison(ds: str) -> ExperimentSpec:
    bridge = "synthetic_demo" if ds == FIXTURE else "flywire_literature"
    return ExperimentSpec(
        name="Virtual fly: baseline vs neural controller (food arena)",
        template="embodied_controller_comparison",
        dataset_id=ds,
        network=NetworkConfig(mode="full"),
        description="Same arena and seed; the baseline condition walks with a fixed descending "
        "command (no neural model), the neural condition derives the command from "
        "descending-neuron activity driven by odour input.",
        conditions=[
            Condition(name="baseline", params={"controller": "baseline"}),
            Condition(name="neural", params={"controller": "neural"}),
        ],
        embodiment=FlySessionConfig(
            arena=arena_preset("food"),
            bridge=bridge,
            duration_s=2.0,
            baseline=BaselineCommand(forward=1.0, turn=0.0),
        ),
        duration_ms=2000,
        n_trials=1,
        evidence="demonstration" if ds == FIXTURE else "hypothesis",
        assumptions=[
            *LIF_ASSUMPTIONS,
            "Leg kinematics come from FlyGym's HybridTurningController, not from the connectome.",
            "Odour field is an analytic FlyMind model.",
        ],
    )


def embodied_silencing(ds: str) -> ExperimentSpec:
    # Silence the steering DN that carried the turning signal in the intact closed loop
    # (fixture: DN_turn_R; FlyWire v783: DNa02 left, see docs/evidence/embodied-flywire.md).
    if ds == FIXTURE:
        bridge, sil = "synthetic_demo", S(group="dn_turn_r")
    else:
        bridge, sil = "flywire_literature", S(group="dna02_left")
    return ExperimentSpec(
        name="Virtual fly: locomotion after neuronal silencing",
        template="embodied_silencing",
        dataset_id=ds,
        network=NetworkConfig(mode="full"),
        description="Neural controller in the food arena, intact vs with a steering descending "
        "group silenced (output blocked).",
        conditions=[
            Condition(name="intact"),
            Condition(
                name="silenced",
                interventions=[
                    InterventionSpec(kind="silence", selector=sil, label="steering DN silenced")
                ],
            ),
        ],
        embodiment=FlySessionConfig(
            arena=arena_preset("food"), controller="neural", bridge=bridge, duration_s=2.0
        ),
        duration_ms=2000,
        n_trials=1,
        evidence="demonstration" if ds == FIXTURE else "hypothesis",
        assumptions=LIF_ASSUMPTIONS,
    )


TEMPLATES: dict[str, tuple[str, Callable[[str], ExperimentSpec], tuple[str, ...]]] = {
    "single_neuron_activation": (
        "Single-neuron activation",
        single_neuron_activation,
        (FIXTURE, FW783, FW630),
    ),
    "population_stimulation": (
        "Population stimulation",
        population_stimulation,
        (FIXTURE, FW783, FW630),
    ),
    "silencing": ("Inhibitory / silencing intervention", silencing, (FIXTURE, FW783, FW630)),
    "propagation": ("Propagation across connected regions", propagation, (FIXTURE, FW783)),
    "sensory_circuit": (
        "Sensory activation of a documented circuit",
        sensory_circuit_reproduction,
        (FIXTURE, FW783, FW630),
    ),
    "parameter_comparison": (
        "Comparison of model parameters",
        parameter_comparison,
        (FIXTURE, FW783, FW630),
    ),
    "intact_vs_lesioned": (
        "Intact vs lesioned circuit",
        intact_vs_lesioned,
        (FIXTURE, FW783, FW630),
    ),
    "repeated_stimuli": ("Response to repeated stimuli", repeated_stimuli, (FIXTURE, FW783, FW630)),
    "embodied_controller_comparison": (
        "Virtual fly: baseline vs neural controller",
        embodied_controller_comparison,
        (FIXTURE, FW783),
    ),
    "embodied_silencing": (
        "Virtual fly: locomotion after silencing",
        embodied_silencing,
        (FIXTURE, FW783),
    ),
}


def build_template(key: str, dataset_id: str) -> ExperimentSpec:
    _title, fn, datasets = TEMPLATES[key]
    if dataset_id not in datasets:
        raise ValueError(f"template {key!r} is not defined for dataset {dataset_id!r}")
    spec = fn(dataset_id)
    spec.params = LIFParams()
    return spec

"""Registered dataset adapters."""

from flymind.connectome.adapters.base import AdapterInfo, DatasetAdapter, PlannedAdapter
from flymind.connectome.adapters.flywire import FlyWireFAFB630ShiuAdapter, FlyWireFAFB783Adapter


class BANCAdapter(PlannedAdapter):
    info = AdapterInfo(
        name="BANCAdapter",
        dataset_id="banc_888",
        title="BANC (Brain And Nerve Cord) v888",
        specimen="BANC adult female brain + VNC (Bates et al. 2026)",
        status="planned",
        description="Public (CC BY 4.0, Harvard Dataverse 10.7910/DVN/7WTH1N); adapter not yet "
        "validated, so imports are refused.",
        required_roles=(),
    )


class MaleCNSAdapter(PlannedAdapter):
    info = AdapterInfo(
        name="MaleCNSAdapter",
        dataset_id="male_cns_v1",
        title="Male CNS v1.0 (Janelia)",
        specimen="adult male CNS (Berg et al. 2026)",
        status="planned",
        description="Public (CC BY 4.0); adapter not yet validated, so imports are refused.",
        required_roles=(),
    )


ADAPTERS: list[DatasetAdapter] = [
    FlyWireFAFB783Adapter(),
    FlyWireFAFB630ShiuAdapter(),
    BANCAdapter(),
    MaleCNSAdapter(),
]

__all__ = ["ADAPTERS", "AdapterInfo", "DatasetAdapter"]

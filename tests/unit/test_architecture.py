"""Layering: lower layers never import higher ones."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "flymind"
ORDER = ["common", "connectome", "brain", "visualization", "embodiment", "experiments", "api"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("flymind."):
            out.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("flymind."):
                    out.add(a.name.split(".")[1])
    return out


def test_layering():
    violations = []
    for layer in ORDER:
        allowed = set(ORDER[: ORDER.index(layer) + 1])
        if layer == "visualization":
            allowed -= {"brain"}
        for f in (SRC / layer).rglob("*.py"):
            bad = _imports(f) - allowed
            if bad:
                violations.append(f"{f.relative_to(SRC)} imports {sorted(bad)}")
    assert not violations, violations

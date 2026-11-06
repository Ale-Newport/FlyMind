# Evidence

Everything in this directory was produced by running FlyMind at commit `a4e2bcd`
(branch `feature/flymind-v0.1`) on macOS 27.0.1, Apple M2 Max, 64 GB. Nothing is
illustrative or hand-made. Where something could not be executed, it is marked
**blocked** with the reason.

| Document | Contents |
|---|---|
| [Feature matrix](feature-matrix.md) | What is verified, how, and what is blocked or not implemented |
| [Reproduction of Shiu et al. 2024](reproduction-shiu2024.md) | Sugar GRN → MN9 on the exact v630 network: reproduced |
| [FlyWire v783 experiments](flywire783-experiments.md) | Frequency sweep, silencing and propagation on v783 (simulation output) |
| [Embodied FlyWire runs](embodied-flywire.md) | Baseline vs neural controller, DNa02 silencing (hypothesis tests) |
| [Benchmarks](benchmarks.md) | Measured performance with machine description and command |
| [Test results](test-results.md) | pytest, Vitest, Playwright, ruff and TypeScript output |
| `screenshots/` | Screenshots of the running application (real data and e2e runs) |
| `test-output/` | Raw console output of the test suites |
| `benchmarks/` | Raw benchmark JSON and Markdown |
| `experiments/` | `record.json` and `readouts.csv` of the evidence experiments |

Screenshots of real data show FlyWire data (Dorkenwald et al. 2024; Schlegel et al.
2024), CC BY-NC 4.0 per the FlyWire guidelines, used with attribution.

**Reproduce everything** (needs `make data-flywire data-630`):

```bash
make test-all test-fulldata test-web e2e
make reproduce
make benchmark
```

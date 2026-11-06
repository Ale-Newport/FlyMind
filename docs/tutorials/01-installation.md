# 1. Installation

Requirements: macOS 13+ (Apple Silicon or Intel) or Linux x86-64/arm64, [uv](https://docs.astral.sh/uv/),
Node.js ≥ 20, a C/C++ compiler (Xcode Command Line Tools on macOS: `xcode-select --install`;
`build-essential` on Debian/Ubuntu) for Brian2's Cython code generation, ~2 GB disk
(+0.3 GB for FlyWire v783, +11 GB for skeletons).

```bash
git clone https://github.com/Ale-Newport/FlyMind.git
cd FlyMind
make setup      # Python 3.13 + locked deps (uv), web deps (npm ci), synthetic dataset
make doctor     # checks imports, MuJoCo, datasets
make dev        # API on :8000 + web app on :5173
```

Open <http://127.0.0.1:5173>. Without downloads you can use every module on the clearly
labelled **synthetic** demonstration network.

Linux without a display: MuJoCo needs an OpenGL context only for vision (eye cameras).
Set `MUJOCO_GL=egl` (GPU) or `MUJOCO_GL=osmesa` (CPU, `libosmesa6`) before `make dev`.

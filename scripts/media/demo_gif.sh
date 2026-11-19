#!/usr/bin/env bash
# Record the README demo from the running app and convert it to docs/media/flymind-demo.gif.
# Needs: `make dev` running with FlyWire v783 installed (`make data-flywire`), and ffmpeg.
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 1; }
curl -fsS http://127.0.0.1:8000/api/health >/dev/null || { echo "start the app first: make dev" >&2; exit 1; }

out_dir=apps/web/test-results/demo
rm -rf "$out_dir"
(cd apps/web && npx playwright test -c playwright.screenshots.config.ts demo-video.spec.ts --output test-results/demo)
video=$(find "$out_dir" -name '*.webm' | head -1)
segments=$(find "$out_dir" -name 'demo-segments.json' | head -1)
[ -n "$video" ] && [ -n "$segments" ] || { echo "recording failed" >&2; exit 1; }

# Build an ffmpeg filter that keeps only the recorded scenes (loading waits removed).
filter=$(python3 - "$segments" <<'EOF'
import json, sys
segs = json.load(open(sys.argv[1]))
parts = [f"[0:v]trim={a:.2f}:{b:.2f},setpts=PTS-STARTPTS[s{i}]" for i, (a, b) in enumerate(segs)]
joined = "".join(f"[s{i}]" for i in range(len(segs)))
print(";".join(parts) + f";{joined}concat=n={len(segs)}:v=1:a=0[v]")
EOF
)
mkdir -p docs/media
# 720 px, 10 fps, 96 colours keeps the GIF under ~8 MB (139k-point clouds compress poorly).
ffmpeg -y -loglevel error -i "$video" -filter_complex "$filter;[v]fps=10,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" docs/media/flymind-demo.gif
ls -lh docs/media/flymind-demo.gif

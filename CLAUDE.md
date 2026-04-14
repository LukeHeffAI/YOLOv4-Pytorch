# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PyTorch implementation of YOLOv4 object detection. Uses Darknet-format `.cfg` files to define model architecture and Darknet binary `.weights` files for weight storage (not PyTorch `.pt` files). Targets MS-COCO dataset.

## Environment setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) via `pyproject.toml` + `uv.lock`. PyTorch is pulled from the `cu126` wheel index (works with CUDA 12.x and 13.x drivers).

```bash
uv sync                 # create .venv and install all deps from the lockfile
uv add <pkg>            # add a new dependency
uv run python <script>  # run a command inside the project env
source .venv/bin/activate   # or activate the venv directly
```

## Commands

All commands below assume either an activated `.venv` or prefix with `uv run`.

### Inference
```bash
uv run python detect.py -input ./examples/eagle.jpg -output ./eagle_detect.png
uv run python detect.py -input video.mp4 -output output.mp4 --video --benchmark
```

### Training (requires COCO dataset in ./COCO/2017/)
```bash
uv run python train.py -results ./results/default --epoch_csv --tensorboard
```
Monitor with: `uv run tensorboard --logdir=./results/default/tensorboard`

### Evaluation
```bash
uv run python evaluate.py -cfg ./configs/yolov4.cfg -weights ./weights/myweight.weights
```

### Common flags (all three scripts)
- `-cfg` / `-weights` / `-obj_thresh` / `--letterbox` / `--force_cpu` / `--print_network`

### No test suite
There are no unit tests. Validation is done via COCO mAP evaluation during training and through `evaluate.py`.

## Architecture

### Entry points
Three standalone scripts (`train.py`, `detect.py`, `evaluate.py`) each parse args via `utilities/arguments.py` and build a model from a `.cfg` file.

### Config parsing pipeline
`utilities/configs.py` is the bridge between Darknet config files and PyTorch:
1. `parse_config(path)` reads a `.cfg` file → list of block dicts → `Darknet` model (`model/darknet.py`)
2. Each `[section]` in the `.cfg` maps to a PyTorch `nn.Module` in `model/layers/`
3. The `[net]` section becomes a `NetBlock` (`model/net_block.py`) storing all training hyperparameters
4. Layer types: `convolutional`, `route` (concat), `shortcut` (residual add), `maxpool`, `upsample`, `yolo` (detection head)

### Model forward pass
`Darknet.forward()` runs input through all layers sequentially. `RouteLayer` and `ShortcutLayer` reference outputs of earlier layers by index. `YoloLayer` is the output layer — in training mode it computes loss (CIoU + objectness + classification), in eval mode it produces detection predictions.

### Data pipeline
- `datasets/coco.py` — `CocoDataset` wraps pycocotools COCO API; handles COCO 91→80 class mapping
- 50% mosaic augmentation during training (4 images composited), controlled by `mosaic=1` in `.cfg`
- `utilities/augmentations.py` — jitter, HSV shifts, horizontal flip
- `utilities/preprocessing.py` — letterboxing, mosaic assembly, eval preprocessing

### Training specifics
- Gradient accumulation via subdivisions: each "batch" is split into `batch/subdivisions` mini-batches
- SGD with momentum (0.949), learning rate divided by batch size (Darknet convention)
- Learning rate scheduling: burn-in warmup then step-based decay (steps/scales in `.cfg`)
- Random input resizing during training for scale invariance
- Weights saved in Darknet binary format at epoch intervals to `results/weights/`

### Weight format
Darknet binary: 16-byte header (version + imgs_seen counter) followed by float32 parameter values. Loading/saving handled by `utilities/weights.py` and per-layer `load_weights()`/`write_weights()` methods on `ConvolutionalLayer`.

### Inference pipeline
`utilities/inferencing.py`: preprocess → model forward → `extract_detections()` → greedy NMS (`utilities/nms.py`) → coordinate correction back to original image space → draw bounding boxes.

## Key conventions

- Annotations use normalized coordinates (0-1) internally; COCO pixel coordinates are converted on load
- Constants (index offsets, activation slopes, COCO stat indices) are centralized in `utilities/constants.py`
- `ImageInfo` (`utilities/image_info.py`) tracks augmentation metadata for coordinate correction during inference
- Available model configs: `yolov4.cfg`, `yolov3.cfg`, `yolov3-spp.cfg`, `yolov3-tiny.cfg` in `configs/`

## Live Streaming

### Architecture
Camera (Pi/laptop) → RTSP via ffmpeg → GPU Server (FastAPI + YOLOv4) → MJPEG → Browser viewer

### Starting the server
```bash
# Streaming deps (fastapi, uvicorn[standard]) are already in pyproject.toml — uv sync installs them

# Start with RTSP source (requires mediamtx running on :8554)
uv run python -m streaming.server --source rtsp://localhost:8554/camera

# Start with local USB camera
uv run python -m streaming.server --source /dev/video0

# Start with a video file (for testing)
uv run python -m streaming.server --source ./examples/video.mp4

# Custom config
uv run python -m streaming.server --source rtsp://localhost:8554/camera -cfg ./configs/yolov3-tiny.cfg -weights ./weights/yolov3-tiny.weights --port 8085
```
Open `http://<server-ip>:8085/` in a browser to view the live detection stream.

### Camera client (Pi/laptop)
```bash
# Stream USB camera to server via RTSP
./streaming/camera_client.sh <SERVER_IP>
./streaming/camera_client.sh 192.168.1.100 /dev/video0 1280x720 15
```
Requires ffmpeg on the camera device. On Raspberry Pi, auto-detects and uses rpicam-vid for hardware encoding.

### Optional: RTSP relay (mediamtx)
Download from https://github.com/bluenviron/mediamtx/releases and run `./mediamtx` on the server. Decouples camera and server lifecycles — camera can reconnect without restarting the server.

### Server endpoints
- `GET /` — Viewer page
- `GET /stream` — MJPEG video stream
- `GET /stats` — JSON (fps, latency, detection count, connection status)
- `POST /config` — Update obj_thresh at runtime (`{"obj_thresh": 0.5}`)

### Viewer controls
- Confidence threshold slider (live update)
- Pause/resume, screenshot, fullscreen
- Keyboard: Space=pause, S=screenshot, F=fullscreen, C=toggle controls

### Streaming module files
- `streaming/server.py` — FastAPI app, FrameGrabber, inference loop, MJPEG endpoint
- `streaming/viewer.html` — Single-file browser viewer (inline CSS/JS, no build step)
- `streaming/camera_client.sh` — ffmpeg RTSP push script for Pi/laptop

## Agents and Skills (.claude/)

This project has custom Claude Code agents and skills configured in `.claude/`. Use them for planning, implementation, and review.

### Agents (.claude/agents/)

Agents are specialist personas invoked via the `Agent` tool with `subagent_type`. They provide domain expertise for planning and implementation.

| Agent | File | When to use |
|-------|------|-------------|
| **backend-engineer** | `agents/backend-engineer.md` | APIs, server-side code, database design, concurrency, caching, streaming protocols |
| **frontend-engineer** | `agents/frontend-engineer.md` | UI components, React/TypeScript, CSS, accessibility, browser-based displays |
| **modern-stack-advisor** | `agents/modern-stack-advisor.md` | Tool/framework selection, architecture decisions, dependency choices. Always web-searches before recommending |
| **ux-design-advisor** | `agents/ux-design-advisor.md` | Interaction design, UI patterns, accessibility, user flows. Never removes features — only shapes how they're presented |
| **systems-architect** | `agents/systems-architect.md` | Large refactors, architecture migrations, module restructuring, cross-cutting concerns |
| **dev-orchestrator** | `agents/dev-orchestrator.md` | Parallel task execution. Takes a plan and dispatches tasks in dependency-ordered waves to worker agents |
| **ml-engineer** | `agents/ml-engineer.md` | ML pipelines, model training/deployment, feature engineering, inference optimization |
| **engineer** | `agents/engineer.md` | General full-stack implementation — the default for tasks that don't fit a specialist |
| **data-analyst** | `agents/data-analyst.md` | Data exploration, SQL, statistical analysis, visualization, A/B tests |

**Usage pattern for planning:** Consult `modern-stack-advisor` for optimal technology choices, `backend-engineer` for server/API design and other backend work, `frontend-engineer` for UI architecture and other frontend work, `ux-design-advisor` for interaction patterns (prerequisite to frontend changes), and `systems-architect` for overall system design. Then use `dev-orchestrator` to parallelize implementation.

**Usage pattern for implementation:** Delegate tasks to the appropriate specialist (`backend-engineer`, `frontend-engineer`, `ml-engineer`, `engineer`) via the `Agent` tool. For example, if implementing a new feature that requires a backend API and a frontend UI, the `systems-architect` might create a plan that includes tasks for both the `backend-engineer` and `frontend-engineer`, and then use `dev-orchestrator` to execute those tasks in parallel.

### Skills (.claude/skills/)

Skills are invoked via `/skill-name` (slash commands). They encode multi-step workflows.

| Skill | Invocation | Purpose |
|-------|-----------|---------|
| **issue-solver** | `/issue-solver NUMBER` | Fetches a GitHub issue, confirms scope, plans solution, delegates to specialist agents. Coordinator — never implements directly |
| **pr-reviewer** | `/pr-reviewer NUMBER` | Fetches a PR, reviews changes, resolves conflicts, delegates domain review to specialists, pushes fixes, replies to comments |
| **git-detective** | `/git-detective DESCRIPTION` | Git forensics — finds lost/overwritten/reverted code in history. Uses pickaxe search, reflog, blame archaeology |
| **ask-for-help** | (auto-triggered) | Guardrail that fires when Claude can't access external resources. 2-strike rule: try once, retry once, then ask the user |
| **workflow-optimizer** | `/workflow-optimizer` or (proactive) | Identifies inefficiencies and proposes new skills/agents/hooks. Scans for repetition, error patterns, blind spots |

### How agents collaborate

Several agents are designed to consult each other:
- `backend-engineer` and `frontend-engineer` both proactively consult `ux-design-advisor` when their decisions affect user-facing behavior
- `systems-architect` orchestrates across all specialists and uses `dev-orchestrator` for parallel execution
- `issue-solver` reads issues and delegates to the right specialist agent based on domain
- `pr-reviewer` spawns specialist agents for domain-specific review (ML code → `ml-engineer`, UI → `frontend-engineer`, etc.)

### Settings (.claude/settings.local.json)

Pre-approved tool permissions are configured in `settings.local.json`. Currently allows: GitHub web fetch, nvidia-smi, pyenv, conda, git, and python version checks without prompting.

---
name: viralmint-runpod-comfyui
description: ViralMint RunPod GPU pods and ComfyUI LTX 2.3 video workflow integration. Use when working on AI Video, RunPod deploy/setup, ComfyUI-Manager installs, workflow mapping, pod status, or img2vid generation in this repo.
---

# ViralMint RunPod + ComfyUI

## Architecture (decisions)

- **RunPod Pods** (not serverless): GPU at `https://{pod_id}-8188.proxy.runpod.net`
- **No shell bootstrap** for models: use **ComfyUI-Manager HTTP API** from the app (same as UI missing-models flow)
- **No ComfyUI browser** required for setup or generate
- **Raw httpx** to `rest.runpod.io` and ComfyUI — no official RunPod Python SDK
- Workflow: **API JSON** only (`video_ltx2_3_ia2v-api.json`); UI export (`video_ltx2_3_ia2v.json`) is for editing in ComfyUI only

## Code map

| Concern | Location |
|---------|----------|
| Pod deploy config | `backend/runpod/pod_config.py` |
| Model URLs | `backend/runpod/models_manifest.json` |
| Custom node packs | `backend/runpod/custom_nodes_manifest.json` |
| Runtime node patches | `backend/workflows/runpod_mapping.json` |
| Manager HTTP | `backend/services/runpod_manager.py` |
| Setup (nodes + models) | `backend/services/runpod_setup.py` → `setup_pod()`, `assess_pod()` |
| RunPod REST + generate | `backend/services/runpod_service.py` |
| REST API | `backend/api/runpod.py`, `backend/api/generate.py` (`POST /runpod`) |
| Background job | `runpod_install_models` → `run_install_runpod_models` in `task_runner.py` |
| UI | `frontend/src/pages/AiVideo.jsx`, `RunPodStatusCard.jsx` |

## Env (`.env`)

```env
RUNPOD_API_KEY=rpa_...          # required for AI Video
RUNPOD_HF_TOKEN=hf_...          # optional, gated HuggingFace files
RUNPOD_NETWORK_VOLUME_ID=vol_... # optional, persist models across pods
```

BYOK also via Settings (`runpod_api_key_encrypted`, `runpod_pod_id`).

## User flow

1. **Deploy Pod** → `POST /api/runpod/deploy` (creates/resumes pod `video generation`)
2. Wait **ComfyUI up** on status (`GET /api/runpod/status` → `comfy_ready`)
3. **Setup pod** → `POST /api/runpod/setup` (alias `/install-models`) queues Manager installs
4. **Restart ComfyUI** on pod after custom nodes finish (nodes do not appear in `object_info` until restart)
5. Poll until `can_generate` (nodes + all 5 models present)
6. **Generate** → `POST /api/generate/runpod` with prompt, start image, reference audio, length_seconds

Status exposes `activity_line`, `setup_job`, `manager_queue` for the live log on AI Video page.

## ComfyUI-Manager API (from app)

All via `runpod_manager.py` (tries `/path` and `/api/path`):

| Action | Endpoint |
|--------|----------|
| Queue custom node pack | `POST /manager/queue/install` |
| Queue model file | `POST /manager/queue/install_model` |
| Start queue | `GET /manager/queue/start` |
| Queue progress | `GET /manager/queue/status` |
| Readiness | `GET /object_info` (node types), `GET /models` (files) |

Do **not** reintroduce `install_models.sh` / `dockerStartCmd` curl bootstrap unless the user explicitly asks.

## Workflow mapping (wired)

| Input | Node | Key |
|-------|------|-----|
| Prompt | `340:319` | `value` |
| Duration (seconds) | `340:331` | `value` (PrimitiveFloat) |
| Start image | `269` | `image` |
| Reference audio | `276` | `audio` (required) |

Uploads use ComfyUI `POST /upload/image` for both image and audio. Job uses `POST /prompt` + poll `GET /history/{id}` + `GET /view`.

## Changing models or nodes

1. Edit workflow in ComfyUI → re-export **API** JSON → update `runpod_mapping.json` if node IDs changed
2. Add new files to `models_manifest.json` and/or `custom_nodes_manifest.json`
3. Run **Setup pod** on a test pod; verify `assess_pod()` / status flags

## Implementation rules

- **Minimize scope** — one manifest as source of truth; no duplicate wget scripts
- **Model downloads**: ComfyUI-RunpodDirect `POST /server_download/start` (same as UI Download to Pod), then `/download_model`, then Manager fallback
- **Do not** use `yarn test` for whole suite; run single test file if tests are added
- **Rebuild** `frontend/dist` when changing `frontend/src` if app serves static dist
- **`can_generate`** = `comfy_ready` + `custom_nodes_ready` + `models_ready`
- Job type stays `runpod_install_models` (DB/WS compatibility); user-facing label is "Setup pod"

## Not wired yet (do not assume)

See [reference.md](reference.md) § Missing wiring for seed, FPS, resolution, negative prompt, prompt expansion (`TextGenerateLTX2Prompt`), stop pod, auto-setup, longer timeouts, etc.

## Quick debug

```bash
# Pod ComfyUI health
curl -s "https://POD_ID-8188.proxy.runpod.net/system_stats"

# Manager queue
curl -s "https://POD_ID-8188.proxy.runpod.net/manager/queue/status"
```

On failure: check Manager security level on pod, ComfyUI logs, and whether restart was done after node installs.

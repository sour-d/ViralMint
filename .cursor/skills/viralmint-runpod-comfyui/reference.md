# ViralMint RunPod + ComfyUI — reference

## Pod configuration (`pod_config.py`)

| Setting | Value |
|---------|--------|
| Name | `video generation` |
| Image | `runpod/comfyui:latest` |
| Template | `cw3nka7d08` |
| GPU | 1× RTX 3090, Community Cloud |
| Disk | 50 GB container + 200 GB volume @ `/workspace` |
| ComfyUI URL | `https://{pod_id}-8188.proxy.runpod.net` |
| ComfyUI path on pod | `/workspace/runpod-slim/ComfyUI` (typical) |

## Models (`models_manifest.json`)

| File | Folder |
|------|--------|
| `ltx-2.3-22b-dev-fp8.safetensors` | checkpoints |
| `ltx-2.3-22b-distilled-lora-384.safetensors` | loras |
| `gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors` | loras |
| `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | latent_upscale_models |
| `gemma_3_12B_it_fp4_mixed.safetensors` | text_encoders |

## Custom node packs (`custom_nodes_manifest.json`)

| Pack ID | Repo | Covers |
|---------|------|--------|
| `comfyui-ltxvideo` | Lightricks/ComfyUI-LTXVideo | `LTXV*`, `LTXAV*`, `TextGenerateLTX*`, `EmptyLTXV*` |
| `comfymath` | evanspearman/ComfyMath | `ComfyMathExpression` |

Built-in core (no pack): `ResizeImageMaskNode`, `ResizeImagesByLongerEdge`, `TrimAudioDuration`, standard loaders, etc. If missing → ComfyUI image too old.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/runpod/status` | Pod + ComfyUI + readiness + `activity_line` |
| POST | `/api/runpod/deploy` | Create/start pod |
| POST | `/api/runpod/setup` | Start setup job (nodes + models) |
| POST | `/api/runpod/install-models` | Alias of setup |
| POST | `/api/generate/runpod` | Queue video generation |

## Status fields

| Field | Meaning |
|-------|---------|
| `comfy_ready` | Port 8188 responds |
| `custom_nodes_ready` | All workflow `class_type`s in `object_info` |
| `models_ready` | All manifest files in `/models` |
| `can_generate` | All three ready |
| `can_setup` | Comfy up but nodes or models missing |
| `setup_in_progress` | Starting pod, setup job, or incomplete readiness |
| `activity_line` | One-line log for UI |

## Setup job flow (`setup_pod`)

1. `manager_available()` probe
2. `_setup_nodes()` — compare `object_info` vs workflow class types → queue `install` for missing packs → `queue_start`
3. `_setup_models()` — compare `/models` vs manifest → queue `install_model` → `queue_start`

Returns `{ ok, message, custom_nodes: {...}, models: {...} }`.

## Generate flow (`run_comfy_img2vid`)

1. Upload start image + audio to ComfyUI input folder
2. `build_workflow()` deep-copy API JSON + patch mapping keys
3. `POST /prompt` → poll history (default 1800s timeout)
4. Download output via `/view`

## Workflow nodes not exposed in app

Defaults remain from export unless mapping extended:

| Control | Node(s) | Notes |
|---------|---------|--------|
| Frame rate | `340:323` | Default 24 |
| Width / height | `340:299`, `340:301`, math | Default ~1920×1080 chain |
| Seed | `340:285`, `340:286` | Fixed in export |
| Negative prompt | CLIP encode nodes | Baked in graph |
| Samplers / CFG / sigmas | Multiple nodes | Fixed |
| Prompt expansion | `340:342` TextGenerateLTX2Prompt | Consumes `340:319`; may rewrite user prompt |
| Output prefix | `341` SaveVideo | `video/LTX_2.3_ia2v` |

## Missing wiring checklist (future work)

**Infrastructure**

- [ ] UI/API to stop or terminate pod (billing)
- [ ] Auto-detect “nodes installed but not loaded” → prompt restart
- [ ] Optional `RUNPOD_NETWORK_VOLUME_ID` in Settings UI
- [ ] Increase or configure `wait_for_comfy_output` timeout for long clips
- [ ] ComfyUI version / core-node guard with clear error

**Product / API**

- [ ] Expose seed (mapping + AiVideo field)
- [ ] Expose FPS and/or resolution presets (9:16, 16:9)
- [ ] Negative prompt or bypass TextGenerateLTX2Prompt if raw prompt desired
- [ ] Auto-setup after deploy (optional flag)
- [ ] Per-model download progress in status
- [ ] Structured ComfyUI error messages in UI

**Workflow hygiene**

- [ ] Confirm checkpoint HF URL matches working repo (`LTX-2.3` vs `LTX-2.3-fp8`)
- [ ] Strip placeholder filenames from API export when re-saving workflow

## Anti-patterns (rejected in this project)

- Curl `install_models.sh` on `dockerStartCmd` at boot (removed; use Manager API)
- Placeholder `runpod_img2vid.json` workflow
- Duplicating Manager HTTP in multiple service files
- Requiring ComfyUI web UI for normal operation
- `yarn test` full suite in agent sessions

## Commits (reference)

- `28043e0` — LTX 2.3 workflow + Manager model installs
- `45c4cdd` — Refactor: `runpod_setup`, `runpod_manager`, status activity line

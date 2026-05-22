# RunPod ComfyUI workflows

## Files

| File | Use |
|------|-----|
| `video_ltx2_3_ia2v-api.json` | API workflow — sent to ComfyUI `POST /prompt` |
| `video_ltx2_3_ia2v.json` | UI export — edit in ComfyUI only |
| `runpod_mapping.json` | Runtime patches (prompt, duration, image, audio) |
| `../runpod/models_manifest.json` | Model files for ComfyUI-Manager |
| `../runpod/custom_nodes_manifest.json` | Custom node packs (LTXVideo, ComfyMath) |

## Setup (from the app)

After **ComfyUI up**, click **Setup pod** (`POST /api/runpod/setup`). Backend code lives in `backend/services/runpod_setup.py` and talks to ComfyUI-Manager on the pod (install node packs, then models, start queue).

Optional `.env`:

```env
RUNPOD_API_KEY=rpa_...
RUNPOD_HF_TOKEN=hf_...              # gated HuggingFace files only
RUNPOD_NETWORK_VOLUME_ID=vol_...     # persist models across new pods (paid)
```

## Per-job uploads

Image and reference audio are uploaded from the app on each generate (ComfyUI `/upload/image`). No manual copy to the pod.

## Status flags

- **ComfyUI up** — port 8188 responds
- **Models ready** — all files in `models_manifest.json` appear in `GET /models`
- **Can generate** — both true

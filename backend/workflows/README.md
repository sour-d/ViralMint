# RunPod ComfyUI workflows

## Files

| File | Use |
|------|-----|
| `video_ltx2_3_ia2v-api.json` | API workflow — sent to ComfyUI `POST /prompt` |
| `video_ltx2_3_ia2v.json` | UI export — edit in ComfyUI only |
| `runpod_mapping.json` | Runtime patches (prompt, duration, image, audio) |
| `../runpod/models_manifest.json` | Models to install via `POST /api/runpod/install-models` |

## Models

After the pod shows **ComfyUI up**, click **Install models** on the AI Video page. That queues downloads on the pod through ComfyUI-Manager (`POST /manager/queue/install_model`), same as the missing-models dialog in the ComfyUI UI.

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

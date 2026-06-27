# Session Context — Niche 2 (anime-lofi) Pipeline

## Goal
Complete anime-lofi pipeline: LLM script with video prompts → Z-turbo txt2img → LTX img2vid (5s default, then trim) → audio-aligned durations → concat final video with master audio; ComfyUI Setup with three per-workflow model management cards.

## Naming
- Backend Python module: `anime_lofi` (snake_case)
- API prefix: `/api/anime-lofi` (kebab-case)
- Frontend route: `/anime-lofi`
- Frontend component: `AnimeLofiStudio`
- Workflow files: `anime_lofi_img2vid.json`, `anime_lofi_txt2img.json`, `runpod_mapping_anime_lofi.json`
- Storage: `storage/anime_lofi`
- Job types: `anime_lofi_generate_videos`, `anime_lofi_generate_images`
- ComfyUI setup kind strings: `z-turbo`, `ltx-img2vid` (these are NOT renamed)
- Note: `niche1` remains unchanged; only `niche2` → `anime-lofi`

## Constraints & Preferences
- LTX is unreliable for <3s or fractional durations — always generate 5s from ComfyUI then trim with ffmpeg `-t <float>`.
- Segment audio durations come from Whisper word timestamps aligned to LLM voiceover text by word-count proportion.
- Compiled video must strip any audio from LTX segment clips (`-map 0:v:0 -map 1:a:0`) and use the master TTS audio track.
- LLM prompt enforces "Statue Rule" (character frozen, no movement) + "Sluggish Environment" + fixed prefix/suffix to prevent character melting in LTX.
- `str.format()` on prompt template must escape `{` / `}` in user idea to avoid `KeyError`.
- Frontend HTTP timeout raised from 30s → 120s to accommodate slow LLM calls (4096 max_tokens).
- Image and video card previews fixed to 2 per row with `xs={6}`, `maxWidth: 320`.

## Pipeline Steps (5-step stepper in AnimeLofiStudio)
1. **Script** — LLM generates JSON with `voiceover_text`, `image_prompt`, `video_prompt` per segment
2. **Audio** — TTS generates voiceover audio file
3. **Images** — Whisper transcribes audio with word timestamps, aligns segment durations, Z-turbo generates images per segment
4. **Videos** — LTX generates 5s video per segment image, trims to aligned duration
5. **Render Final** — Concat all video segments with master audio (stripping LTX audio)

## Key Decisions
- **Always generate 5s LTX video then trim**: LTX is unreliable for fractional/very short durations.
- **Separate retry-video / retry-image endpoints**: Each creates a single-segment background job.
- **`-map` instead of `-an`**: Explicitly maps video stream from concat and audio from master track.
- **Three ComfyUI setup cards**: LTX Audio→Video, LTX Image→Video, Z-turbo Image.
- **Word-count alignment for durations**: LLM segments mapped to Whisper word timestamps by counting words.
- **Frontend timeout 120s**: LLM calls with 4096 max_tokens can exceed 30s.

## Critical Context
- LTX model detection uses RunpodDirect's `check_missing_models` endpoint — not ComfyUI `/models`.
- `z_image_turbo_bf16.safetensors` directory mismatch (`unet/` on disk vs `diffusion_models` in manifest) doesn't break detection because RunpodDirect searches recursively.
- Image/video generation both run as sequential background jobs (one ComfyUI queue per segment).
- `filter_missing_model_entries` falls through to RunpodDirect disk check.

## Key Files
- `backend/services/anime_lofi_llm.py`: LLM prompt with video_prompt + Statue Rule + stationary poses
- `backend/services/anime_lofi_comfy.py`: txt2img + img2vid ComfyUI service (build workflows, submit, download, trim)
- `backend/services/anime_lofi_service.py`: full pipeline (transcribe, align durations, generate images, generate videos, compile)
- `backend/workflows/runpod_mapping_anime_lofi.json`: mapping with `txt2img` and `img2vid` sections
- `backend/workflows/anime_lofi_img2vid.json`: LTX img2vid workflow
- `backend/workflows/anime_lofi_txt2img.json`: Z-turbo txt2img workflow
- `backend/runpod/models_manifest.json`: models tagged `["ltx", "ltx-img2vid"]` / `["z-turbo"]`
- `backend/services/runpod_setup.py`: `/models` list parsing, per-workflow checks, skip node check for `ltx-img2vid`
- `backend/api/runpod.py`: workflow/setup/models-status/delete-models for `ltx|ltx-img2vid|z-turbo`
- `backend/api/anime_lofi.py`: transcribe+align, image/video async gen, retry per segment, compilation
- `backend/core/task_runner.py`: `run_anime_lofi_generate_images`, `run_anime_lofi_generate_videos`
- `frontend/src/pages/ComfyUISetup.jsx`: three-card layout
- `frontend/src/pages/AnimeLofiStudio.jsx`: 5-step pipeline, per-segment image/video cards with retry
- `frontend/src/api/http.js`: timeout 120s

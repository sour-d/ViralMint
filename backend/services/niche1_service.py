"""Niche 1 — Podcast Quote Shorts pipeline.
Image → Script → Audio → Lip-sync → Captions + Music
"""
import json
import logging
import random
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from backend.config import settings
from backend.core.ai_provider import get_ai_client, AIProvider
from backend.services.runpod_service import (
    run_comfy_img2vid, get_comfy_base_url, get_pod_status,
)
from backend.core.api_keys import get_runpod_api_key, get_runpod_pod_id

logger = logging.getLogger(__name__)

STORAGE = Path("storage/niche1")
BASE_DIR = STORAGE / "base"
VARIANTS_DIR = STORAGE / "variations"
OUTPUT_DIR = STORAGE / "output"
MEMORY_FILE = STORAGE / "memory.json"

TOPICS = [
    "self love", "confidence", "letting go", "growth mindset",
    "relationships", "healing", "purpose", "happiness",
    "overcoming fear", "inner peace", "motivation", "respect",
]


def _ensure_dirs():
    for d in (BASE_DIR, VARIANTS_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── Memory ─────────────────────────────────────────────────────────────

def load_memory() -> dict:
    _ensure_dirs()
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except Exception:
            pass
    return {"scripts": [], "images": [], "videos": []}


def save_memory(memory: dict):
    _ensure_dirs()
    MEMORY_FILE.write_text(json.dumps(memory, indent=2, default=str))


# ── Step 1: Image Variation ────────────────────────────────────────────

async def list_base_images() -> list[dict]:
    _ensure_dirs()
    images = []
    for f in sorted(BASE_DIR.iterdir()):
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            images.append({
                "filename": f.name,
                "path": str(f),
                "url": f"/api/niche1/media/{quote(f.name)}",
            })
    return images


async def generate_image_variation(
    base_filename: str,
    description: str = "",
    user_settings=None,
) -> dict:
    """Take a base image and generate a variation via OpenRouter image gen."""
    _ensure_dirs()
    base_path = BASE_DIR / base_filename
    if not base_path.exists():
        raise FileNotFoundError(f"Base image not found: {base_filename}")

    variations = [
        "different earrings and a slightly different outfit color",
        "subtle hairstyle change, different dress, minimal makeup",
        "different necklace, hair slightly tied back, casual top",
        "wearing a different top, small smile change, different earrings",
        "hair in a different style, no earrings, different colored outfit",
        "slightly different makeup, hair down instead of tied, casual look",
        "different outfit color, subtle lighting change, warm expression",
        "hair style changed, wearing a necklace, slight head tilt",
    ]
    variation = random.choice(variations)

    base_desc = description.strip() or "A woman sitting in a cozy podcast studio with warm lighting, speaking naturally"

    gen_prompt = (
        f"{base_desc}\n\n"
        f"Variation: {variation}. "
        f"Keep the same person's face and identity. "
        f"Photorealistic, natural lighting, podcast studio background."
    )

    filename = f"var_{uuid.uuid4().hex[:8]}.png"
    output_path = VARIANTS_DIR / filename

    try:
        import openai as _openai
        from backend.core.crypto import decrypt_safe

        # Resolve API key for image generation (OpenRouter or OpenAI)
        user_enc = getattr(user_settings, "ai_api_key_encrypted", None) if user_settings else None
        user_provider = getattr(user_settings, "ai_provider", "") if user_settings else ""
        or_key = (decrypt_safe(user_enc) or "") if user_enc and user_provider == "openrouter" else ""
        oai_key = (decrypt_safe(user_enc) or "") if user_enc and user_provider == "openai" else ""
        or_key = or_key or settings.OPENROUTER_API_KEY or ""
        oai_key = oai_key or settings.OPENAI_API_KEY or ""

        success = False
        # Try OpenRouter first
        if or_key:
            try:
                client = _openai.AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1", timeout=60)
                resp = await client.images.generate(
                    model="black-forest-labs/flux-schnell",
                    prompt=gen_prompt, n=1, size="1024x1024", response_format="b64_json",
                )
                import base64 as _b64
                output_path.write_bytes(_b64.b64decode(resp.data[0].b64_json))
                success = True
            except Exception as e1:
                logger.warning(f"OpenRouter image gen failed: {e1}")

        # Fall back to OpenAI
        if not success and oai_key:
            try:
                client = _openai.AsyncOpenAI(api_key=oai_key, timeout=60)
                resp = await client.images.generate(
                    model="dall-e-3", prompt=gen_prompt, n=1, size="1024x1024",
                    response_format="b64_json",
                )
                import base64 as _b64
                output_path.write_bytes(_b64.b64decode(resp.data[0].b64_json))
                success = True
            except Exception as e2:
                logger.warning(f"OpenAI image gen failed: {e2}")

        if not success:
            logger.warning("No image API key available, copying base image instead")
            import shutil
            shutil.copy2(base_path, output_path)
    except Exception as e:
        logger.warning(f"Image generation failed ({e}), copying base instead")
        import shutil
        shutil.copy2(base_path, output_path)

    memory = load_memory()
    entry = {
        "id": str(uuid.uuid4()),
        "base_image": base_filename,
        "variation": filename,
        "description": gen_prompt,
        "variation_applied": variation,
        "created_at": datetime.utcnow().isoformat(),
    }
    memory["images"].append(entry)
    save_memory(memory)

    return {
        "id": entry["id"],
        "filename": filename,
        "path": str(output_path),
        "url": f"/api/niche1/media/{filename}",
    }


# ── Step 2: Script Generation ─────────────────────────────────────────

async def generate_script(
    topic: str = None,
    user_settings=None,
    custom_instructions: str = "",
) -> dict:
    """Generate an emotional quote script with memory to avoid repetition."""
    _ensure_dirs()
    memory = load_memory()
    past_scripts = [s["script"][:100] for s in memory["scripts"][-20:]]
    past_summary = "\n".join(f"- {s}" for s in past_scripts) if past_scripts else "None"

    if not topic:
        topic = random.choice(TOPICS)

    ai = get_ai_client(user_settings)
    prompt = (
        f"You are a writer for emotional quote shorts. "
        f"Write a short, powerful monologue (40-60 seconds when spoken, ~100-150 words) "
        f"about '{topic}'.\n\n"
        f"Style: intimate, warm, like a close friend sharing wisdom. "
        f"Open with a relatable statement, build emotional depth, end with an uplifting resolution.\n\n"
        f"Recently written topics (DO NOT repeat these):\n{past_summary}\n\n"
        f"Requirements:\n"
        f"- Natural spoken English, no markdown\n"
        f"- Conversational tone, like someone reflecting aloud\n"
        f"- One central emotional idea, keep it focused\n"
        f"- Suitable for a close-up video with soft background music\n"
        f"- End with a memorable one-liner or affirmation\n"
        f"{custom_instructions}\n\n"
        f"Return ONLY the script text. No title, no labels."
    )

    script = await ai.chat(messages=[{"role": "user", "content": prompt}], max_tokens=1024)
    script = script.strip()

    entry = {
        "id": str(uuid.uuid4()),
        "topic": topic,
        "script": script,
        "created_at": datetime.utcnow().isoformat(),
    }
    memory["scripts"].append(entry)
    save_memory(memory)

    return {"id": entry["id"], "topic": topic, "script": script}


# ── Step 3: Audio Generation ──────────────────────────────────────────

async def generate_audio(
    script: str,
    voice: str = "en-US-AndrewMultilingualNeural",
    user_settings=None,
) -> dict:
    """Generate TTS audio from script."""
    _ensure_dirs()
    from backend.services.tts_service import generate_tts, TTSProvider

    api_key = ""
    provider = TTSProvider.EDGE_TTS
    if user_settings:
        if getattr(user_settings, "tts_provider", None) == "openai_tts":
            provider = TTSProvider.OPENAI_TTS
            api_key = getattr(user_settings, "openai_api_key", "") or settings.OPENAI_API_KEY

    audio_path = await generate_tts(
        text=script,
        provider=provider,
        voice_id=voice,
        api_key=api_key,
    )

    filename = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    final_path = OUTPUT_DIR / filename
    import shutil
    shutil.copy2(audio_path, final_path)

    return {"filename": filename, "path": str(final_path), "url": f"/api/niche1/media/{filename}"}


async def generate_audio_for_user(
    script: str,
    user_settings=None,
) -> dict:
    """Wraps generate_audio for API calls."""
    voice = "en-US-AndrewMultilingualNeural"
    if user_settings and getattr(user_settings, "preferred_tts_voice", None):
        voice = user_settings.preferred_tts_voice
    return await generate_audio(script, voice=voice, user_settings=user_settings)


# ── Step 4: Lip-sync Video via ComfyUI ────────────────────────────────

async def generate_lipsync(
    image_filename: str,
    audio_filename: str,
    user_id: str = "local",
    user_settings=None,
    on_progress=None,
) -> dict:
    """Run ComfyUI LTX img2vid with audio conditioning on RunPod."""
    _ensure_dirs()
    image_path = VARIANTS_DIR / image_filename
    if not image_path.exists():
        image_path = BASE_DIR / image_filename
    audio_path = OUTPUT_DIR / audio_filename

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_filename}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_filename}")

    api_key = get_runpod_api_key(user_settings)
    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await get_pod_status(api_key, stored_pod_id)
    if not status.get("can_generate"):
        raise RuntimeError(f"RunPod not ready: {status.get('message', 'unknown')}")

    base_url = get_comfy_base_url(status["pod_id"])
    output_filename = f"lipsync_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / output_filename

    audio_duration = 30
    try:
        from backend.services.video_utils import probe_duration
        audio_duration = int(probe_duration(audio_path)) + 1
    except Exception:
        pass

    await run_comfy_img2vid(
        base_url=base_url,
        prompt="A woman speaking naturally in a podcast studio, subtle head movements, gentle expressions, warm lighting, cinematic, 24fps",
        start_image_path=image_path,
        length_seconds=max(audio_duration, 15),
        output_path=output_path,
        audio_path=audio_path,
        on_progress=on_progress,
    )

    memory = load_memory()
    entry = {
        "id": str(uuid.uuid4()),
        "image": image_filename,
        "audio": audio_filename,
        "video": output_filename,
        "created_at": datetime.utcnow().isoformat(),
    }
    memory["videos"].append(entry)
    save_memory(memory)

    return {"id": entry["id"], "filename": output_filename, "path": str(output_path)}


# ── Step 5: Post-processing (caps + music) ───────────────────────────

async def finalize_video(
    video_filename: str,
    script: str,
    user_settings=None,
) -> dict:
    """Add animated captions and background music to the lip-sync video."""
    _ensure_dirs()
    video_path = OUTPUT_DIR / video_filename
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_filename}")

    from backend.services.whisper_service import whisper_service
    from backend.services.caption_service import generate_captions_ass, burn_captions
    from backend.services.music_service import select_music, mix_audio
    from backend.services.ffmpeg_service import add_audio_to_video

    # 1. Transcribe for word timestamps
    whisper_service.load("fast")
    result = await whisper_service.transcribe(video_path, language=None)
    segments = result.get("segments", [])

    # 2. Burn captions
    cap_style = "glow"
    if user_settings and getattr(user_settings, "caption_style", None):
        cap_style = user_settings.caption_style

    ass_path = await generate_captions_ass(
        segments=segments,
        style=cap_style,
        aspect_ratio="9:16",
        emoji_style="moderate",
    )
    captioned = await burn_captions(video_path, ass_path)

    # 3. Add background music
    music_path = await select_music(genre="lofi")
    final_path = OUTPUT_DIR / f"final_{uuid.uuid4().hex[:8]}.mp4"
    import shutil
    shutil.copy2(captioned, final_path)

    if music_path:
        try:
            mixed = await mix_audio(
                voice_path=final_path,
                music_path=music_path,
                music_volume_db=-22.0,
            )
            mixed_final = OUTPUT_DIR / f"final_{uuid.uuid4().hex[:8]}.mp4"
            await add_audio_to_video(final_path, mixed, mixed_final)
            final_path = mixed_final
        except Exception as e:
            logger.warning(f"Music mix failed: {e}")

    result = {
        "filename": final_path.name,
        "path": str(final_path),
        "url": f"/api/niche1/media/{final_path.name}",
        "script": script,
    }
    return result

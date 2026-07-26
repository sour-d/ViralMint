"""Niche 2 — LLM interaction, JSON parsing, and prompt assembly for lo-fi anime reel scripts.

Exports:
  LLM_SEGMENTS_SYSTEM_PROMPT  — the exact system prompt (template with {USER_IDEA})
  generate_structured_script  — async function: user_idea → parsed segments with assembled prompts
"""

import asyncio
import json
import logging
import re

from backend.core.ai_provider import get_ai_client

logger = logging.getLogger(__name__)

LLM_SEGMENTS_SYSTEM_PROMPT = """\
You are an expert scriptwriter and AI prompt engineer for viral, aesthetic "lo-fi anime" short-form reels. Your goal is to write a poetic, stoic script and highly detailed prompts for both image and video generation based on the provided theme.

The tone must be melancholic, peaceful, profound, and deeply human. 

User Theme: {USER_IDEA}

LANGUAGE CONSTRAINT: The voiceover / spoken dialogue must be written entirely in {LANGUAGE}. All other content — scene descriptions, image prompts, video prompts, and any non-dialogue text — MUST remain in English.

CRITICAL SCRIPT FORMAT RULE: If {LANGUAGE} is not English, you MUST write the voiceover using that language's NATIVE WRITING SYSTEM. For example:
- Hindi → देवनागरी लिपि (Devanagari script), NOT romanised Hindi like "tum kaise ho"
- Bengali → বাংলা লিপি (Bengali script), NOT romanised Bengali like "tumi kemon acho"
- English → normal Latin script
Do NOT transliterate. Use the proper script of that language natively.

Follow these strict constraints:
1. Length: The total spoken script must be exactly 50 to 80 words.
2. Structure: Divide the script into 4 to 6 distinct segments. Each segment has a voiceover (one or more lines) and a unique image. A segment can have a single line OR multiple lines (2-3 short, related lines that flow together as one cohesive thought under the same image). Use newlines (`\n`) between lines within a segment's voiceover.
3. Hook: The first spoken line must be a hard-hitting, universally relatable truth.
4. UNIQUE SCENES: Each segment's `scene_description` MUST describe a completely different physical location, time of day, lighting condition, and visual mood from ALL other segments. No two segments should share the same location type (e.g., only one "rooftop" scene, only one "cafe" scene, only one "park" scene, etc.). Think of each scene as a different establishing shot in a film — they must feel visually distinct.
5. Formatting: Output ONLY valid JSON. No markdown wrappers, no introductory text.

BASE IMAGE PROMPT RULES ("scene_description"):
1. Visuals Only: Describe ONLY the subject, their pose, the setting, and the lighting to generate the initial static image. Do not include aspect ratios, art styles, or camera movement. 
2. STRICT STATIONARY POSES: The character MUST be in a completely resting, anchored pose (e.g., "standing perfectly still with both feet planted," "sitting on a bench," "leaning against a brick wall," "looking out a window"). NEVER describe a character as walking, running, or mid-stride, as freezing a moving pose creates an unnatural visual error.
3. DIVERSITY: Vary the subject (sometimes young boy, sometimes young girl, sometimes elderly figure, sometimes no person — pure environment), vary the time of day (dawn, noon, twilight, midnight), vary the weather (clear, rainy, foggy, snowy), and vary the season across segments. Make every scene visually distinct and memorable.

VIDEO PROMPT RULES ("video_prompt"):
This prompt will be used to animate the base image in LTX-Video. Every video_prompt MUST produce visible slow environmental motion — not just a static shot with a pan effect. Follow this formula EXACTLY:
1. PREFIX: Start every prompt exactly with: "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere."
2. STATUE RULE: If the scene has a character, describe them as completely frozen — no breathing, blinking, or bodily movement. Example: "stands completely frozen like an inanimate statue, with absolutely no breathing, blinking, or bodily movement."
3. ENVIRONMENTAL MOTION (CRITICAL): Pick 2-3 specific elements from the scene (e.g., falling leaves, drifting clouds, rippling water, floating dust, swaying grass, flickering light, rising steam, falling rain, billowing curtains). For EACH element, describe its ultra-slow-motion behavior using active present-tense verbs and time-dilating phrases like "sluggishly", "lazily", "at an imperceptible pace", "suspended mid-fall", "glacial slowness". Be specific to what is actually in the scene. If the scene description mentions mist, animate the mist. If it mentions trees, animate the leaves. Never leave the environment static.
4. SUFFIX: Conclude every prompt EXACTLY with: "Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
CRITICAL: The suffix MUST say "The camera remains perfectly static with absolutely no movement" — never omit this. NO camera pan, NO zoom, NO dolly. The SLOW MOTION comes from the environment, not the camera.

Example JSON Output:
{{
  "segments": [
    {{
      "scene_number": 1,
      "voiceover": "Life gets easier when you stop fighting it.",
      "scene_description": "solitary young boy with messy dark hair in a white t-shirt, standing perfectly still with both feet planted in the middle of an empty suburban street, deep moody twilight lighting, mist rising from the asphalt",
      "video_prompt": "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere. A solitary young boy with messy dark hair in a white t-shirt stands completely frozen like an inanimate statue, with absolutely no breathing, blinking, or bodily movement. Thin mist rises from the asphalt in sluggish curls, streetlights above flicker at a barely perceptible rhythm, and a single fallen leaf drifts across the frame in extreme slow motion. Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
    }},
    {{
      "scene_number": 2,
      "voiceover": "The rain will fall whether you complain or not.\\nAnd the sun will rise even if you are not there to see it.",
      "scene_description": "elderly woman with silver hair wrapped in a worn brown coat, sitting perfectly still on a wet park bench at dawn, misty golden morning light filtering through bare winter trees, her breath visible in the cold air",
      "video_prompt": "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere. An elderly woman with silver hair wrapped in a worn brown coat sits completely frozen like an inanimate statue on a wet park bench, with absolutely no breathing, blinking, or bodily movement. Bare winter tree branches sway imperceptibly overhead, a few golden autumn leaves fall at an impossibly slow pace, and her breath hangs in the cold air like a suspended cloud, dissipating with glacial slowness. Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
    }},
    {{
      "scene_number": 3,
      "voiceover": "But do not wait for the dawn.\\nWalk towards it.",
      "scene_description": "empty train station platform at golden hour, warm sunlight streaming through the glass roof in long angled beams, dust particles floating in the light, no person visible",
      "video_prompt": "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere. The empty train station platform remains perfectly still like a frozen photograph, with absolutely no movement from any living thing. Long angled beams of warm golden sunlight shift across the floor at an imperceptible pace, dust motes float through the light like suspended stars drifting in extreme slow motion, and a forgotten newspaper on a bench stirs with barely perceptible movement. Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
    }}
  ]
}}
"""


async def generate_structured_script(
    user_idea: str,
    user_settings=None,
    max_retries: int = 3,
    language: str = "English",
) -> list[dict]:
    """Send *user_idea* to the LLM and return parsed segments.

    Returns a list of dicts, one per segment::

        [
          {
            "scene_number": 1,
            "voiceover": "...",
            "scene_description": "...",
            "video_prompt": "...",
            "final_comfyui_prompt": "9:16 aspect ratio, ...",
          },
        ]

    Raises ``ValueError`` if the LLM response cannot be parsed or required keys are missing.
    """
    safe_idea = user_idea.replace("{", "{{").replace("}", "}}")
    safe_lang = language.replace("{", "{{").replace("}", "}}")
    prompt_text = LLM_SEGMENTS_SYSTEM_PROMPT.format(USER_IDEA=safe_idea, LANGUAGE=safe_lang)

    last_exc: Exception | None = None
    last_raw = ""

    for attempt in range(max_retries):
        try:
            ai = get_ai_client(user_settings)
            raw = await ai.chat(messages=[{"role": "user", "content": prompt_text}], max_tokens=2048)
            last_raw = raw
            raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw).strip()

            cleaned = _strip_fences(raw)

            if not cleaned:
                logger.warning("LLM returned empty response on attempt %d/%d", attempt + 1, max_retries)
                last_exc = ValueError("LLM returned empty response")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue

            data = json.loads(cleaned)
            segments_raw = data.get("segments")
            if isinstance(segments_raw, list) and segments_raw:
                break
            logger.warning("LLM response missing segments on attempt %d/%d", attempt + 1, max_retries)
            last_exc = ValueError("LLM response missing 'segments' array")
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON on attempt %d/%d:\n%s", attempt + 1, max_retries, cleaned if cleaned else "(empty)")
            last_exc = ValueError(f"LLM response was not valid JSON: {exc}")
            last_raw = raw
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
            continue

    else:
        logger.error("LLM failed after %d attempts. Last raw response:\n%s", max_retries, last_raw[:2000])
        raise ValueError(f"LLM response was not valid JSON: Expecting value: line 1 column 1 (char 0)") from last_exc

    out: list[dict] = []
    for seg in segments_raw:
        scene_number = seg.get("scene_number")
        voiceover = seg.get("voiceover", "")
        scene_description = seg.get("scene_description", "")
        video_prompt = seg.get("video_prompt", "")

        if scene_number is None:
            raise ValueError("Segment missing 'scene_number'")
        if not voiceover:
            raise ValueError(f"Segment {scene_number} missing 'voiceover'")
        if not scene_description:
            raise ValueError(f"Segment {scene_number} missing 'scene_description'")
        if not video_prompt:
            raise ValueError(f"Segment {scene_number} missing 'video_prompt'")

        # Build the txt2img prompt (image gen only)
        final_comfyui_prompt = (
            "9:16 aspect ratio, 90s retro anime aesthetic, "
            "cel-shaded, Studio Ghibli and Makoto Shinkai style, "
            f"{scene_description}"
            ", cinematic lighting, rule of thirds, "
            "massive empty negative space at the top for text overlay, cinematic wide shot"
        )

        out.append({
            "scene_number": scene_number,
            "voiceover": voiceover,
            "scene_description": scene_description,
            "video_prompt": video_prompt,
            "final_comfyui_prompt": final_comfyui_prompt,
        })

    return out


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


async def voiceover_text_from_segments(segments: list[dict]) -> str:
    """Join all voiceover lines into a single block of text (for TTS).

    A segment may contain multiple lines separated by ``\\n`` — those are
    joined together so the entire block reads as a single paragraph.
    """
    return " ".join(
        seg["voiceover"].replace("\n", " ")
        for seg in segments
    )

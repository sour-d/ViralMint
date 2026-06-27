"""Niche 2 — LLM interaction, JSON parsing, and prompt assembly for lo-fi anime reel scripts.

Exports:
  LLM_SEGMENTS_SYSTEM_PROMPT  — the exact system prompt (template with {USER_IDEA})
  generate_structured_script  — async function: user_idea → parsed segments with assembled prompts
"""

import json
import logging
import re

from backend.core.ai_provider import get_ai_client

logger = logging.getLogger(__name__)

LLM_SEGMENTS_SYSTEM_PROMPT = """\
You are an expert scriptwriter and AI prompt engineer for viral, aesthetic "lo-fi anime" short-form reels. Your goal is to write a poetic, stoic script and highly detailed prompts for both image and video generation based on the provided theme.

The tone must be melancholic, peaceful, profound, and deeply human. 

User Theme: {USER_IDEA}

Follow these strict constraints:
1. Length: The total spoken script must be exactly 50 to 80 words.
2. Structure: Divide the script into 5 to 10 distinct segments. Each segment must be a short, single-breath phrase (roughly 5-12 words). Use natural punctuation as segment boundaries — each comma-separated clause or short sentence is its own segment. Do not merge multiple ideas into one segment.
3. Hook: The first spoken line must be a hard-hitting, universally relatable truth.
4. Formatting: Output ONLY valid JSON. No markdown wrappers, no introductory text.

BASE IMAGE PROMPT RULES ("scene_description"):
1. Visuals Only: Describe ONLY the subject, their pose, the setting, and the lighting to generate the initial static image. Do not include aspect ratios, art styles, or camera movement. 
2. STRICT STATIONARY POSES: The character MUST be in a completely resting, anchored pose (e.g., "standing perfectly still with both feet planted," "sitting on a bench," "leaning against a brick wall," "looking out a window"). NEVER describe a character as walking, running, or mid-stride, as freezing a moving pose creates an unnatural visual error.

VIDEO PROMPT RULES ("video_prompt"):
This prompt will be used to animate the base image in LTX-Video. You MUST strictly enforce the following formula to prevent character melting:
1. Prefix: Start every prompt exactly with: "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere."
2. The Statue Rule: Describe the stationary character from the base image but explicitly add that they are frozen. Example: "The character stands completely frozen like an inanimate statue, with absolutely no breathing, blinking, or bodily movement."
3. Sluggish Environment Rule: Describe the environment moving in extreme slow motion using active, present-tense verbs and time-dilating keywords (e.g., "sluggishly rippling," "lazily drifting," "slowly flickering," "falling at an imperceptible pace"). Be specific to the scene elements present:
   - Clouds: "The clouds in the sky drift at a practically imperceptible, hypnotic pace, their shapes subtly stretching like slow breath."
   - Trees / leaves: "The tree leaves flutter and sway in ultra-slow motion, each leaf tracing a lazy, dreamlike arc through the air before settling."
   - Water / rain: "The rain falls in thick, sluggish streaks, each droplet suspended mid-fall for an impossibly long moment before continuing its slow descent."
   - Curtains / fabric: "The curtain billows outward in extreme slow motion, the fabric undulating like a gentle underwater wave."
   - Smoke / steam: "Tendrils of smoke curl upward with glacial slowness, twisting into lazy spirals that hang in the air."
   - Light / shadows: "The shadows of passing clouds slide across the ground in ultra-slow-motion, and distant warm lights flicker gently at a barely perceptible rhythm."
   - Dust / particles: "Tiny dust motes float and drift through the air in extreme slow motion, catching the light like suspended stars."
   - Grass / crops: "The field of grass ripples in a sluggish, wave-like motion, stalks bending and swaying as if underwater, each blade moving independently with dreamlike slowness."
4. Suffix: Conclude every prompt exactly with: "Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."

Example JSON Output:
{{
  "segments": [
    {{
      "scene_number": 1,
      "voiceover": "Life gets easier when you stop fighting it.",
      "scene_description": "solitary young boy with messy dark hair in a white t-shirt, standing perfectly still with both feet planted in the middle of an empty suburban street, deep moody twilight lighting",
      "video_prompt": "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere. A solitary young boy with messy dark hair in a white t-shirt stands completely frozen like an inanimate statue, with absolutely no breathing, blinking, or bodily movement. A gentle, ultra-slow motion breeze causes the power lines above to sway sluggishly, looking almost suspended in time. Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
    }},
    {{
      "scene_number": 2,
      "voiceover": "The rain will fall whether you complain or not.",
      "scene_description": "solitary young girl looking out a rain-streaked cafe window, sitting perfectly still at a small wooden table, dark rainy night, glowing warm yellow interior lights",
      "video_prompt": "9:16 vertical video, 90s retro anime aesthetic, nostalgic lo-fi art style. Ultra-slow motion, dreamy, lingering and melancholic atmosphere. A solitary young girl sitting at a small wooden table looking out a cafe window remains completely frozen like an inanimate statue, with absolutely no breathing, blinking, or bodily movement. Heavy continuous rain falls straight down outside the window at a sluggish, slow-motion pace, illuminated by the slowly flickering warm streetlights. Heavy film grain, muted vintage colors. The camera remains perfectly static with absolutely no movement."
    }}
  ]
}}
"""


async def generate_structured_script(
    user_idea: str,
    user_settings=None,
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
    prompt_text = LLM_SEGMENTS_SYSTEM_PROMPT.format(USER_IDEA=safe_idea)

    ai = get_ai_client(user_settings)
    raw = await ai.chat(messages=[{"role": "user", "content": prompt_text}], max_tokens=4096)
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw).strip()

    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON:\n%s", cleaned)
        raise ValueError(f"LLM response was not valid JSON: {exc}") from exc

    segments_raw = data.get("segments")
    if not isinstance(segments_raw, list) or not segments_raw:
        raise ValueError("LLM response missing 'segments' array or it is empty")

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
    """Join all voiceover lines into a single block of text (for TTS)."""
    return " ".join(seg["voiceover"] for seg in segments)

# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Auto-write an LTX-2.3 video prompt from a start image + reference audio.

Works for:
  - pure music / instrumental — uses BPM + beat timestamps as motion cues
  - dialog / speech / voice-over — uses Whisper word timestamps as cues
  - songs with vocals — uses BOTH beats and lyrics

Pipeline:
  1. `analyze_audio()`  — librosa: BPM, beat times, energy, key, plus a
                          speech-vs-music classifier and (if speech is
                          present) a faster-whisper transcript with word
                          timestamps. CPU only.
  2. `synthesize_prompt()` — single multimodal LLM call (free OpenRouter
                              vision model by default) that takes the image
                              + audio feature blob and returns:
                                { audio_kind, genre, mood, energy_label, prompt }
                              `prompt` is a timestamped LTX prompt aligned
                              to the relevant cues (beats / words / both).

The LLM acts as classifier+writer, so we don't ship a 300 MB music-tagging
CNN locally; Whisper is the only model that downloads (~500 MB once).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from backend.core.ai_provider import AIClient, AIProvider, get_ai_client

logger = logging.getLogger(__name__)


# Curated list of free vision-capable models on OpenRouter, tried in order.
# OpenRouter rotates :free models frequently — when this list goes stale,
# we automatically fall back to a live `/api/v1/models` query (see
# `_discover_free_vision_models`).
FREE_VISION_MODELS_OPENROUTER = [
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

# Cache the discovered free-vision list across calls so we don't hit the
# OpenRouter models endpoint on every Auto-write click. 1 hour is plenty.
_DISCOVERY_CACHE_TTL_S = 3600
_discovery_cache: dict = {"at": 0.0, "models": []}

# Audio is analysed at 22.05 kHz mono — librosa default, good enough for
# BPM/beats/centroid and keeps memory low on the laptop.
SAMPLE_RATE = 22050
# Cap analysis to this many seconds so a 5-minute song doesn't burn 30s of CPU.
MAX_ANALYSIS_SECONDS = 90

# Map a 12-bin chroma argmax to musical key names. Major/minor distinction is
# rough — we use harmonic content energy to break the tie. Good enough as a
# hint, not a transcription.
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class TranscriptWord:
    word: str
    start: float
    end: float


@dataclass
class AudioFeatures:
    duration_s: float
    bpm: float
    beats_s: list[float]               # downsampled beat timestamps (first 32)
    rms_mean: float
    rms_peak: float
    energy_label: str                  # "low" | "medium" | "high"
    spectral_centroid_hz: float        # brightness proxy
    brightness_label: str              # "dark" | "balanced" | "bright"
    key_guess: str                     # e.g. "F minor" — best-effort hint
    harmonic_ratio: float              # 0..1, harmonic energy fraction
    percussive_ratio: float            # 0..1, percussive energy fraction
    voice_band_ratio: float            # 0..1, fraction of energy in 80–1000 Hz
    audio_kind: str                    # "speech" | "song_with_vocals" | "music"
    has_speech: bool                   # True if we ran Whisper and got text
    language: Optional[str] = None
    transcript: str = ""
    transcript_words: list[TranscriptWord] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transcript_words"] = [asdict(w) for w in self.transcript_words]
        return d


# ── 1. Audio analysis (CPU-only, librosa + optional whisper) ──────────────────

async def analyze_audio(path: Path, length_seconds: int) -> AudioFeatures:
    """
    Pull tempo/beat/energy/key features and (when the clip is speech or has
    vocals) a Whisper transcript with word-level timestamps.
    """
    import librosa  # local import — keeps fastapi startup snappy

    duration_cap = min(MAX_ANALYSIS_SECONDS, max(length_seconds * 2, 30))
    y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True, duration=duration_cap)
    duration_s = float(librosa.get_duration(y=y, sr=sr))

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    rms = librosa.feature.rms(y=y).flatten()
    rms_mean = float(np.mean(rms))
    rms_peak = float(np.max(rms)) if rms.size else 0.0

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr).flatten()
    centroid_mean = float(np.mean(centroid)) if centroid.size else 0.0

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    pitch_class = int(np.argmax(np.mean(chroma, axis=1)))
    key_guess = KEY_NAMES[pitch_class]

    y_harm, y_perc = librosa.effects.hpss(y)
    eh = float(np.mean(librosa.feature.rms(y=y_harm)))
    ep = float(np.mean(librosa.feature.rms(y=y_perc)))
    total = max(eh + ep, 1e-8)
    harmonic_ratio = eh / total
    percussive_ratio = ep / total

    voice_band_ratio = _voice_band_energy_ratio(y, sr)

    if percussive_ratio > 0.55:
        key_guess += " (likely minor)"
    elif percussive_ratio < 0.35 and harmonic_ratio > 0.65:
        key_guess += " (likely major)"

    energy_label = _bucket(rms_mean, [0.04, 0.12], ["low", "medium", "high"])
    brightness_label = _bucket(
        centroid_mean,
        [1500.0, 3500.0],
        ["dark", "balanced", "bright"],
    )

    beats_trimmed = [round(float(t), 2) for t in beat_times if t <= length_seconds]
    if len(beats_trimmed) > 32:
        step = math.ceil(len(beats_trimmed) / 32)
        beats_trimmed = beats_trimmed[::step][:32]

    # Librosa-only is unreliable at separating speech from bass-heavy music
    # (both pile energy into 80–1000 Hz). We use it ONLY to decide whether
    # to invoke Whisper; the transcript is the source of truth for kind.
    speech_likely_hint = voice_band_ratio > 0.40

    transcript = ""
    transcript_words: list[TranscriptWord] = []
    language: Optional[str] = None
    has_speech = False
    if speech_likely_hint:
        try:
            tx = await _transcribe(path, length_seconds)
            transcript = tx["text"]
            language = tx["language"]
            transcript_words = tx["words"]
            has_speech = _transcript_is_meaningful(transcript, transcript_words)
        except Exception as e:
            logger.warning("DEBUG:: whisper transcription failed: %s", e)

    word_count = len(transcript_words)
    transcript_span_s = (
        (transcript_words[-1].end - transcript_words[0].start)
        if len(transcript_words) >= 2 else 0.0
    )
    audio_kind = _classify_audio_kind(
        has_speech=has_speech,
        percussive_ratio=percussive_ratio,
        bpm=bpm,
        rms_mean=rms_mean,
        transcript=transcript,
        word_count=word_count,
        transcript_span_s=transcript_span_s,
    )

    return AudioFeatures(
        duration_s=round(duration_s, 2),
        bpm=round(bpm, 1),
        beats_s=beats_trimmed,
        rms_mean=round(rms_mean, 4),
        rms_peak=round(rms_peak, 4),
        energy_label=energy_label,
        spectral_centroid_hz=round(centroid_mean, 1),
        brightness_label=brightness_label,
        key_guess=key_guess,
        harmonic_ratio=round(harmonic_ratio, 3),
        percussive_ratio=round(percussive_ratio, 3),
        voice_band_ratio=round(voice_band_ratio, 3),
        audio_kind=audio_kind,
        has_speech=has_speech,
        language=language,
        transcript=transcript,
        transcript_words=transcript_words,
    )


def _voice_band_energy_ratio(y: "np.ndarray", sr: int) -> float:
    """Fraction of spectral energy in 80–1000 Hz — the speech fundamentals band."""
    import librosa
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    band_mask = (freqs >= 80.0) & (freqs <= 1000.0)
    if not band_mask.any():
        return 0.0
    total = float(np.sum(S))
    if total <= 0.0:
        return 0.0
    band = float(np.sum(S[band_mask, :]))
    return band / total


def _classify_audio_kind(
    *,
    has_speech: bool,
    percussive_ratio: float,
    bpm: float,
    rms_mean: float,
    transcript: str = "",
    word_count: int = 0,
    transcript_span_s: float = 0.0,
) -> str:
    """
    Whisper-grounded classifier. This is now a HINT only — the LLM gets
    final say via the `audio_kind` field in its JSON response.

    Reasoning:
      - Sports commentary, podcasts, news, narration all have crowd noise
        or ambient bed → percussive_ratio jumps into the 0.30–0.55 band,
        which previously triggered "song_with_vocals" by mistake.
      - Real song lyrics are SHORT (few words / second, with repetition),
        speech is DENSE (many words spread over time).

    Rules:
      - No usable transcript → "music".
      - Lots of words spread over multiple seconds → "speech" regardless of
        percussion (covers commentary, voice-over, narration, dialog).
      - Short transcript + meaningful percussion → "song_with_vocals".
      - Fallback → "speech".
    """
    if not has_speech:
        return "music"

    span = max(transcript_span_s, 0.001)
    words_per_sec = word_count / span if span > 0 else 0.0
    long_speech_block = word_count >= 8 and span >= 3.0

    # Real speech tends to be 1.5–4 words/sec over multiple seconds.
    # Song lyric phrases over a short clip are usually < 1.0 words/sec.
    if long_speech_block and words_per_sec >= 1.2:
        return "speech"

    musical_signal = (
        word_count < 8
        and (
            percussive_ratio > 0.45
            or (bpm >= 100.0 and percussive_ratio > 0.35)
        )
    )
    return "song_with_vocals" if musical_signal else "speech"


def _transcript_is_meaningful(text: str, words: list[TranscriptWord]) -> bool:
    """
    Filter out Whisper hallucinations on near-silent or non-speech audio.
    A real spoken clip yields multiple words spread across the timeline,
    not a single 'Thanks for watching!' artifact on a 5-second instrumental.
    """
    cleaned = (text or "").strip()
    if len(cleaned) < 4:
        return False
    # At least two distinct words with non-zero duration spread.
    if len(words) < 2:
        return False
    span = max(w.end for w in words) - min(w.start for w in words)
    return span >= 0.5


async def _transcribe(path: Path, length_seconds: int) -> dict:
    """Run faster-whisper. Returns {text, language, words: [TranscriptWord,...]}."""
    from backend.services.whisper_service import whisper_service

    result = await whisper_service.transcribe(path)
    text = (result.get("text") or "").strip()
    language = result.get("language")

    words: list[TranscriptWord] = []
    for seg in result.get("segments", []) or []:
        for w in seg.get("words", []) or []:
            start = float(w.get("start", 0.0))
            if start > length_seconds + 0.5:
                break
            words.append(TranscriptWord(
                word=str(w.get("word", "")).strip(),
                start=round(start, 2),
                end=round(float(w.get("end", start)), 2),
            ))
        if words and words[-1].start > length_seconds + 0.5:
            break

    if len(words) > 48:
        step = math.ceil(len(words) / 48)
        words = words[::step][:48]

    return {"text": text, "language": language, "words": words}


def _bucket(value: float, thresholds: list[float], labels: list[str]) -> str:
    for t, lbl in zip(thresholds, labels):
        if value < t:
            return lbl
    return labels[-1]


# ── 2. Multimodal prompt synthesis (vision LLM via OpenRouter) ────────────────

SYNTH_SYSTEM = """You are a video direction assistant for the LTX-2.3 image-to-video model.

YOU MUST DECIDE TWO THINGS BEFORE WRITING THE PROMPT:

1) audio_kind:
   - "speech"            → dialog, vlog, tutorial, monologue, podcast
   - "commentary"        → sports commentary, news, narration, voice-over
   - "song_with_vocals"  → music with sung/rapped lyrics
   - "music"             → pure instrumental, ambient, sound-design
   - "ambient"           → no clear speech and no clear musical beat

2) subject_role — what the person/subject in the image is DOING with the audio:
   - "speaker"           → the subject IS delivering the audio; lip-sync mouth to words.
                           Only choose this if the image shows a vlogger/host/anchor
                           setup (facing camera, mic visible, headset) and the
                           audio's voice plausibly matches the subject.
   - "listener_reactor"  → the subject is HEARING the audio and reacting with facial
                           expressions, head movement, gestures, posture. Default
                           for commentary, news, voice-over, podcast, and for songs
                           when the subject is not on a stage.
   - "performer"         → the subject sings/raps the lyrics. Only if the image
                           clearly shows a performer setup (stage, mic, instrument).
   - "dancer_or_mover"   → the subject moves to instrumental music or a beat.

IMPORTANT for commentary/news/voice-over:
  The subject is almost always a LISTENER_REACTOR — do NOT have them mouth or
  lip-sync the commentator's words. Use facial reactions (smile, surprise,
  squint, head shake, fist pump, clap, lean forward) tied to the EMOTIONAL
  content and pacing of the transcript.

TIMESTAMP RULES (NON-NEGOTIABLE):
- Format MUST be MM:SS with two digits each (e.g. 00:00, 00:03, 00:05).
- The video is exactly N seconds long. The maximum timestamp is 00:0N (or
  longer only if N >= 60). NEVER write a timestamp greater than the video
  length. Do not output 0:39, 0:77, 3:09, or any value with more digits.
- Don't quote the supplied beat-position decimals as if they were timestamps.
  Those are reference data, not clock time.
- One prompt line per timestamp; don't repeat timestamps.

LINE FORMAT:
- "MM:SS — <action describing the subject> + <one concrete visual detail>"
- Camera notes are optional and sparse ("slow push-in"). No jump cuts.
- End with ONE final line "Soundscape: ..." (free text, no timestamp).

CONTENT RULES:
- The subject and setting MUST stay grounded in the supplied image. Do not
  invent new people, locations, clothing, or props.
- For listener_reactor: focus on FACIAL EXPRESSIONS and GESTURES, NOT mouth
  shapes matching words.
- For speaker / performer: lip movement matches transcript / lyrics at their
  word timestamps.
- For dancer_or_mover: motion intensity matches BPM and energy.
"""


def _format_seconds_as_mmss(s: float) -> str:
    s = max(0.0, float(s))
    mm = int(s // 60)
    ss = int(s % 60)
    return f"{mm:02d}:{ss:02d}"


def _format_words_block(words: list[TranscriptWord], length_seconds: int) -> str:
    """One-word-per-line with sub-second precision. Caps near video length."""
    lines: list[str] = []
    for w in words:
        if w.start > length_seconds + 0.5:
            break
        lines.append(f"  {w.start:5.1f}s  \"{w.word}\"")
    if not lines:
        return "  (no word-level timing returned)"
    return "\n".join(lines)


def _format_beats_block(bpm: float, beats: list[float], length_seconds: int) -> str:
    if bpm <= 0:
        return "  (no clear beat detected)"
    period = 60.0 / bpm if bpm > 0 else 0.0
    in_window = [b for b in beats if b <= length_seconds]
    head = (
        f"  BPM: {bpm:.1f}  (one beat every ~{period:.2f}s, "
        f"~{int(length_seconds / max(period, 0.001))} beats in this clip)"
    )
    if not in_window:
        return head
    sample = ", ".join(f"{b:.2f}s" for b in in_window[:8])
    return head + f"\n  First beats (REFERENCE ONLY — do not use as MM:SS): {sample}"


def _build_synth_user_message(audio: AudioFeatures, length_seconds: int) -> str:
    length_padded = _format_seconds_as_mmss(length_seconds)
    has_speech = audio.has_speech and audio.transcript.strip()

    sections: list[str] = []
    sections.append(
        f"REQUESTED VIDEO LENGTH: {length_seconds} seconds "
        f"(timestamps 00:00 → {length_padded} only)"
    )
    sections.append(
        "HEURISTIC HINT (you may override this — your own classification wins):\n"
        f"  audio_kind hint: {audio.audio_kind}"
    )

    audio_summary = [
        f"  duration: {audio.duration_s:.1f}s",
        f"  energy: {audio.energy_label} (rms_mean={audio.rms_mean})",
        f"  brightness: {audio.brightness_label}",
        f"  harmonic/percussive split: {audio.harmonic_ratio:.2f} / {audio.percussive_ratio:.2f}",
        f"  voice-band energy ratio: {audio.voice_band_ratio:.2f}",
    ]
    sections.append("AUDIO FEATURES:\n" + "\n".join(audio_summary))

    if has_speech:
        sections.append(
            f"TRANSCRIPT (Whisper, language={audio.language or 'unknown'}):\n"
            f"  \"{audio.transcript.strip()}\""
        )
        sections.append(
            "WORDS WITH TIMING (use these for word-aligned actions if the "
            "subject is a speaker/performer; otherwise use them only to time "
            "facial REACTIONS to the audio's content):\n"
            + _format_words_block(audio.transcript_words, length_seconds)
        )

    if not has_speech or audio.audio_kind in ("song_with_vocals", "music"):
        sections.append(
            "RHYTHM / BEATS (REFERENCE ONLY — do not output these decimals as "
            "MM:SS timestamps):\n"
            + _format_beats_block(audio.bpm, audio.beats_s, length_seconds)
            + (f"\n  key_guess: {audio.key_guess}" if audio.key_guess else "")
        )

    sections.append(
        "TASK:\n"
        "Look at the start frame and pick the audio_kind and subject_role per "
        "the system rules. Then write 4–8 timestamped lines from 00:00 up to "
        f"{length_padded} describing what the subject does. Add one final "
        "\"Soundscape: ...\" line."
    )
    sections.append(
        "OUTPUT — strict JSON, no markdown fences:\n"
        "{\n"
        '  "audio_kind": "speech|commentary|song_with_vocals|music|ambient",\n'
        '  "subject_role": "speaker|listener_reactor|performer|dancer_or_mover",\n'
        '  "genre": "<short tag, e.g. \'cricket commentary (Hindi)\', \'EDM\', '
        "'lo-fi rap', 'news anchor', 'acoustic ballad'>\",\n"
        '  "mood": "<1-3 adjectives>",\n'
        '  "energy_label": "low|medium|high",\n'
        '  "prompt": "00:00 — ...\\n00:0X — ...\\n...\\nSoundscape: ..."\n'
        "}"
    )

    return "\n\n".join(sections)


IMAGE_CAPTION_SYSTEM = (
    "You are a precise image describer for a video-generation pipeline. "
    "Describe ONLY what is visible: the main subject(s), pose, clothing, "
    "facial expression, setting, lighting, color palette, framing, and any "
    "objects in hand. Be concrete and visual; do not speculate about story, "
    "music, or motion. 4–6 sentences, plain prose, no headings."
)


async def synthesize_prompt(
    image_path: Path,
    audio: AudioFeatures,
    length_seconds: int,
    user_settings=None,
) -> dict:
    """
    Call an LLM and get back
    {audio_kind, genre, mood, energy_label, prompt, model_used}.

    Routing:
      - If the user's BYOK model is text-only (e.g. owl-alpha), we run a
        free vision model FIRST to caption the image, then send the caption
        + audio features to the BYOK as plain text. This lets you use any
        text-only free model as the "brain".
      - Otherwise we send the image + audio features in one multimodal call,
        walking the candidate chain (BYOK if vision-capable → curated free
        vision models → live-discovered free vision models).
    """
    image_data_url = _encode_image_data_url(image_path)
    base_user_text = _build_synth_user_message(audio, length_seconds)

    # Path A: text-only BYOK → caption image first, then ship as text.
    text_only_byok = await _resolve_text_only_byok(user_settings)
    if text_only_byok is not None:
        try:
            caption = await _caption_image_via_vision(
                image_data_url=image_data_url,
                user_settings=user_settings,
            )
        except Exception as e:
            logger.warning(
                "DEBUG:: vision-caption pre-step failed (%s) — falling back "
                "to multimodal chain", e,
            )
            caption = None

        if caption:
            user_text = (
                "IMAGE DESCRIPTION (from a vision model — treat this as the "
                "ground truth of what is visible in the start frame):\n"
                f"{caption}\n\n" + base_user_text
            )
            try:
                logger.info(
                    "DEBUG:: prompt-synth text-only path — caption via vision, "
                    "prompt via %s", text_only_byok.model,
                )
                raw = await text_only_byok.chat(
                    messages=[{"role": "user", "content": user_text}],
                    system=SYNTH_SYSTEM,
                    max_tokens=1400,
                )
                if not raw or not raw.strip():
                    raise RuntimeError(
                        f"{text_only_byok.model} returned empty response"
                    )
                return _finalize_synth_result(
                    raw, audio,
                    used_model=text_only_byok.model,
                    length_seconds=length_seconds,
                )
            except Exception as e:
                if not _is_model_unavailable(e) and "valid JSON" not in str(e) and "empty response" not in str(e):
                    logger.exception(
                        "DEBUG:: text-only BYOK %s fatal error",
                        text_only_byok.model,
                    )
                    raise
                logger.warning(
                    "DEBUG:: text-only BYOK %s unusable (%s) — falling "
                    "back to multimodal chain", text_only_byok.model, e,
                )

    # Path B: multimodal candidate chain.
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": base_user_text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ],
    }]

    candidates = await _vision_client_candidates(user_settings)
    if not candidates:
        raise RuntimeError(
            "No AI key configured. Set OPENROUTER_API_KEY (free vision "
            "models) or ANTHROPIC_API_KEY / OPENAI_API_KEY in .env, or pick "
            "a provider in Settings."
        )

    last_err: Optional[Exception] = None
    result: Optional[dict] = None
    attempts: list[str] = []

    for ai_client in candidates:
        attempts.append(ai_client.model)
        try:
            logger.info(
                "DEBUG:: prompt-synth trying %s (%s)",
                ai_client.model, ai_client.provider.value,
            )
            raw = await ai_client.chat(
                messages=messages,
                system=SYNTH_SYSTEM,
                max_tokens=1400,
            )
        except Exception as e:
            if not _is_model_unavailable(e):
                logger.exception("DEBUG:: prompt-synth fatal error on %s", ai_client.model)
                raise
            logger.warning(
                "DEBUG:: %s unavailable (%s) — falling back to next candidate",
                ai_client.model, e,
            )
            last_err = e
            continue

        # 200 OK doesn't mean usable. Free models often return an empty body,
        # a refusal, or markdown without JSON. Treat any of those as
        # recoverable and move on to the next candidate.
        if not raw or not raw.strip():
            logger.warning(
                "DEBUG:: %s returned an empty body — falling back",
                ai_client.model,
            )
            last_err = RuntimeError(f"{ai_client.model} returned empty response")
            continue
        try:
            result = _finalize_synth_result(
                raw, audio,
                used_model=ai_client.model,
                length_seconds=length_seconds,
            )
            break
        except Exception as e:
            logger.warning(
                "DEBUG:: %s returned unparseable output (%s) — falling back. "
                "First 400 chars: %s",
                ai_client.model, e, (raw or "")[:400],
            )
            last_err = e
            continue

    if result is None:
        tried = ", ".join(attempts) or "(none)"
        raise RuntimeError(
            f"All vision-capable models failed. Tried: {tried}. "
            f"Last error: {last_err}. Click Auto-write again to retry "
            "(free OpenRouter providers often recover within a minute), or "
            "configure ANTHROPIC_API_KEY / OPENAI_API_KEY in .env / Settings."
        )
    return result


def _finalize_synth_result(
    raw: str,
    audio: AudioFeatures,
    *,
    used_model: Optional[str],
    length_seconds: int = 60,
) -> dict:
    parsed = _safe_json_load(raw)
    prompt_text = (parsed.get("prompt") or "").strip()
    if not prompt_text:
        raise RuntimeError(
            "Prompt synthesis returned no prompt. "
            f"Model {used_model} raw output:\n{raw[:600]}"
        )
    prompt_text = _sanitize_prompt_timestamps(prompt_text, length_seconds)
    audio_kind_out = str(parsed.get("audio_kind") or audio.audio_kind).strip()
    subject_role_out = str(parsed.get("subject_role") or "").strip()
    if not subject_role_out:
        # Best-effort fallback so the UI always has a value.
        subject_role_out = (
            "listener_reactor" if audio_kind_out in ("commentary", "speech")
            else "performer" if audio_kind_out == "song_with_vocals"
            else "dancer_or_mover" if audio_kind_out == "music"
            else "listener_reactor"
        )
    return {
        "audio_kind": audio_kind_out,
        "subject_role": subject_role_out,
        "genre": str(parsed.get("genre") or "unknown").strip(),
        "mood": str(parsed.get("mood") or "").strip(),
        "energy_label": str(
            parsed.get("energy_label") or audio.energy_label,
        ).strip().lower(),
        "prompt": prompt_text,
        "model_used": used_model,
    }


# Leading-of-line clock: "00:03", "0:39", "1:5". Normalize + clamp.
_TS_LINE_RE = re.compile(r"(?m)^(\s*)(\d{1,2}):(\d{1,2})(?=\b)")

# Inline clock anywhere in the text (e.g. "...beat at 0:39"). Used to convert
# obvious decimal-seconds-pretending-to-be-timestamps to plain "Xs" notation
# so the reader/UI doesn't get confused. We only touch values that are OUT
# OF RANGE (i.e. cannot be valid MM:SS for this video) — that's the
# fingerprint of the LLM leaking raw beat decimals.
_TS_INLINE_RE = re.compile(r"(?<![\d.])(\d{1,2}):(\d{1,2})(?![\d:])")


def _sanitize_prompt_timestamps(prompt_text: str, length_seconds: int) -> str:
    """
    Defensive cleanup for LLM output:
      - Each leading-of-line clock → padded to MM:SS, clamped to length_seconds.
      - Inline clocks that are OUT OF RANGE (e.g. "0:77" or "3:09" in a 6s clip)
        → rewritten to "<n>s" form, since those are almost certainly the LLM
        echoing decimal beat positions like 0.77 it saw in the analysis blob.
      - Anything else is left alone.
    """
    max_total = max(1, int(length_seconds))

    def _fix_line(match: "re.Match[str]") -> str:
        leading, mm_s, ss_s = match.group(1), match.group(2), match.group(3)
        mm, ss = int(mm_s), int(ss_s)
        total = min(mm * 60 + ss, max_total)
        return f"{leading}{total // 60:02d}:{total % 60:02d}"

    cleaned = _TS_LINE_RE.sub(_fix_line, prompt_text)

    def _fix_inline(match: "re.Match[str]") -> str:
        mm, ss = int(match.group(1)), int(match.group(2))
        total = mm * 60 + ss
        # Valid in-range MM:SS — leave as-is (likely a real timestamp).
        if total <= max_total and ss < 60:
            return match.group(0)
        # Out of range. Almost certainly a decimal beat position quoted as
        # clock time. Rewrite to "Xs" so the prompt still reads.
        approx_s = mm + ss / 100.0  # "0:39" → 0.39s
        return f"~{approx_s:.2f}s"

    return _TS_INLINE_RE.sub(_fix_inline, cleaned)


async def _resolve_text_only_byok(user_settings) -> Optional[AIClient]:
    """
    Return the user's BYOK AIClient IFF it's text-only. Otherwise None.

    For OpenRouter BYOK models we query OpenRouter's /api/v1/models to
    check input_modalities. For Anthropic / OpenAI we trust the keyword
    heuristic (their default models are all vision-capable nowadays).
    """
    try:
        byok = get_ai_client(user_settings)
    except Exception:
        return None

    if byok.provider != AIProvider.OPENROUTER:
        return None

    # Heuristic shortcut: if the name clearly says vision, skip the API call.
    if _looks_vision_capable(byok.model):
        return None

    try:
        is_text_only = not await _model_supports_image_on_openrouter(
            byok.model, byok.api_key,
        )
    except Exception as e:
        logger.warning("DEBUG:: modality check for %s failed (%s) — assuming text-only",
                       byok.model, e)
        is_text_only = True

    return byok if is_text_only else None


async def _caption_image_via_vision(*, image_data_url: str, user_settings) -> str:
    """Pick the first available free vision model and have it caption the image."""
    candidates = await _vision_client_candidates(user_settings)
    # Drop any text-only candidates that may have slipped in (BYOK with weird name).
    last_err: Optional[Exception] = None
    for ai_client in candidates:
        if ai_client.provider == AIProvider.OPENROUTER and not _looks_vision_capable(ai_client.model):
            try:
                ok = await _model_supports_image_on_openrouter(
                    ai_client.model, ai_client.api_key,
                )
            except Exception:
                ok = True
            if not ok:
                continue

        try:
            logger.info("DEBUG:: caption-step trying %s", ai_client.model)
            raw = await ai_client.chat(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this start frame for an image-to-video prompt."},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }],
                system=IMAGE_CAPTION_SYSTEM,
                max_tokens=350,
            )
            caption = (raw or "").strip()
            if caption:
                return caption
        except Exception as e:
            if not _is_model_unavailable(e):
                raise
            logger.warning("DEBUG:: caption model %s unavailable (%s)", ai_client.model, e)
            last_err = e
            continue
    raise RuntimeError(f"No working vision model for image captioning. Last error: {last_err}")


# Modality cache: keyed by (model_id) → bool (supports image input)
_modality_cache: dict[str, dict] = {}
_MODALITY_TTL_S = 3600


async def _model_supports_image_on_openrouter(model_id: str, api_key: str) -> bool:
    """Lookup input_modalities for a single OpenRouter model. Cached.

    Hits the same /api/v1/models endpoint as `_discover_free_vision_models`
    and reuses the discovery cache via `_modality_cache`.
    """
    now = time.time()
    cached = _modality_cache.get(model_id)
    if cached and now - cached["at"] < _MODALITY_TTL_S:
        return cached["image"]

    # Trigger the full discovery; this populates `_modality_cache` for every
    # model the API knows about — including the one we just asked for.
    await _discover_free_vision_models(api_key)

    cached = _modality_cache.get(model_id)
    if cached:
        return cached["image"]

    # Model isn't in the listing (older deprecated id, or a private one).
    # Cache as unknown=False so we don't ask again for an hour.
    _modality_cache[model_id] = {"at": now, "image": False}
    return False


def _is_model_unavailable(exc: Exception) -> bool:
    """
    Return True if we should silently fall through to the next candidate.

    This covers anything that means "this model isn't usable RIGHT NOW":
      - model removed / not found (NotFoundError, 404, "model_not_found")
      - upstream provider hiccup mid-stream
        (openai.APIError: "Provider returned error", "internal server error",
         "bad gateway", "service unavailable", 5xx)
      - rate limits (429)
      - transient connection / timeout errors
      - openai-side BadRequest that the candidate just doesn't accept our
        message shape (e.g. some free models reject base64 image_url)

    NOT recoverable (re-raised):
      - AuthenticationError (401)  — user must fix their key
      - PermissionDeniedError (403) — user must enable access
    """
    try:
        from openai import (  # type: ignore
            APIConnectionError,
            APIError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            PermissionDeniedError,
        )
    except Exception:
        APIConnectionError = APIError = APIStatusError = APITimeoutError = ()  # type: ignore
        AuthenticationError = PermissionDeniedError = ()  # type: ignore

    # Hard stops — user error, not a model rotation problem.
    if AuthenticationError and isinstance(exc, AuthenticationError):
        return False
    if PermissionDeniedError and isinstance(exc, PermissionDeniedError):
        return False

    # Anything else from the openai client → treat as transient/per-model.
    if APIError and isinstance(exc, (APIError, APIConnectionError, APITimeoutError)):
        return True
    if APIStatusError and isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status is None or status >= 400:
            return True

    msg = (str(exc) or "").lower()
    return any(
        s in msg for s in (
            "no endpoints found",
            "404",
            "model_not_found",
            "model not found",
            "not_found_error",
            "provider returned error",
            "provider error",
            "rate limit",
            "rate_limit",
            "too many request",
            "internal server error",
            "bad gateway",
            "service unavailable",
            "overloaded",
            "timeout",
            "timed out",
            "connection error",
            "429",
            "500",
            "502",
            "503",
            "504",
            "529",
        )
    )


async def _vision_client_candidates(user_settings) -> list[AIClient]:
    """
    Build the ordered candidate list of vision-capable AIClients.
      1. User's BYOK model if it looks vision-capable.
      2. Curated free OpenRouter vision models.
      3. Live-discovered free OpenRouter vision models (anything else
         the API currently advertises with input_modalities=['image'] and
         id ending in ':free').
    """
    candidates: list[AIClient] = []
    seen: set[str] = set()

    try:
        byok = get_ai_client(user_settings)
    except Exception as e:
        logger.warning("DEBUG:: no BYOK AI client (%s)", e)
        byok = None

    if byok and _looks_vision_capable(byok.model):
        candidates.append(byok)
        seen.add(byok.model)

    from backend.config import settings as app_settings
    or_key = app_settings.OPENROUTER_API_KEY
    if or_key:
        for model_id in FREE_VISION_MODELS_OPENROUTER:
            if model_id in seen:
                continue
            candidates.append(AIClient(
                provider=AIProvider.OPENROUTER,
                api_key=or_key,
                model=model_id,
            ))
            seen.add(model_id)

        try:
            discovered = await _discover_free_vision_models(or_key)
        except Exception as e:
            logger.warning("DEBUG:: free-vision discovery failed: %s", e)
            discovered = []
        for model_id in discovered:
            if model_id in seen:
                continue
            candidates.append(AIClient(
                provider=AIProvider.OPENROUTER,
                api_key=or_key,
                model=model_id,
            ))
            seen.add(model_id)

    if not candidates and byok:
        # No vision-capable option found anywhere — try BYOK anyway so the
        # error message says exactly which model was tried.
        candidates.append(byok)

    return candidates


async def _discover_free_vision_models(api_key: str) -> list[str]:
    """Live-query OpenRouter for any :free model that accepts image input.

    Side effect: populates `_modality_cache` for every returned model so
    follow-up `_model_supports_image_on_openrouter` calls hit the cache
    without an extra HTTP round-trip.
    """
    now = time.time()
    if (
        _discovery_cache["models"]
        and now - _discovery_cache["at"] < _DISCOVERY_CACHE_TTL_S
    ):
        return _discovery_cache["models"]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    found: list[str] = []
    for m in data.get("data", []) or []:
        mid = m.get("id") or ""
        if not mid:
            continue
        modalities = (m.get("architecture") or {}).get("input_modalities") or []
        supports_image = "image" in modalities
        _modality_cache[mid] = {"at": now, "image": supports_image}
        if mid.endswith(":free") and supports_image:
            found.append(mid)

    _discovery_cache["at"] = now
    _discovery_cache["models"] = found
    logger.info("DEBUG:: discovered %d free vision models on OpenRouter", len(found))
    return found


def _looks_vision_capable(model: Optional[str]) -> bool:
    if not model:
        return False
    m = model.lower()
    return any(tag in m for tag in (
        "vision", "vl-", "-vl", "claude-3", "claude-4", "claude-opus",
        "claude-sonnet", "claude-haiku", "gpt-4o", "gpt-5", "gemini",
        "llama-3.2", "qwen2-vl", "qwen2.5-vl", "pixtral", "internvl",
    ))


def _encode_image_data_url(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in ("jpg", "jpe"):
        mime = "image/jpeg"
    elif ext in ("jpeg", "png", "webp", "gif", "bmp"):
        mime = f"image/{ext}"
    else:
        mime = "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _safe_json_load(text: str) -> dict:
    """Strip ```json fences if the model added them, then json.loads."""
    s = text.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model did not return valid JSON: {e}\n--- raw ---\n{text[:800]}") from e

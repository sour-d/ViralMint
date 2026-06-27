"""Subtitle overlay via moviepy TextClip — 9:16 vertical video (1080×1920)."""
from pathlib import Path
from moviepy.editor import TextClip, CompositeVideoClip

_FONT_PATH = str(Path(__file__).resolve().parent.parent.parent / "font" / "PlayfairDisplay-VariableFont_wght.ttf")


def add_subtitle(
    video_clip,
    text: str,
    start_time: float,
    end_time: float,
    position=("center", "center"),
    font_path: str = _FONT_PATH,
    font_size: int = 60,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2,
    text_width: int = 850,
    fade_duration: float = 0.3,
):
    """Overlay a subtitle on *video_clip* from *start_time* to *end_time*.

    Parameters
    ----------
    video_clip : VideoFileClip
        The base video.
    text : str
        Subtitle text.
    start_time : float
        When the subtitle appears (seconds).
    end_time : float
        When the subtitle disappears (seconds).
    position : tuple, optional
        ``("center", "center")`` or ``("center", y)`` for a fixed Y offset.
    font_path : str
        Path to the TrueType font file.
    font_size : int
    color : str
    stroke_color : str
    stroke_width : int
    text_width : int
        Max width in pixels — text wraps automatically.
    fade_duration : float
        Crossfade in/out duration (seconds).

    Returns
    -------
    CompositeVideoClip
        The composited clip with the subtitle layer.
    """
    duration = end_time - start_time

    txt_clip = (
        TextClip(
            text,
            fontsize=font_size,
            font=font_path,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method="caption",
            size=(text_width, None),
            align="center",
        )
        .set_start(start_time)
        .set_duration(duration)
        .set_position(position)
        .crossfadein(fade_duration)
        .crossfadeout(fade_duration)
    )

    return CompositeVideoClip([video_clip, txt_clip], size=video_clip.size)

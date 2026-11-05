"""Interviewer portraits: one generated image per persona (optional course task).

The persona already changes how the coach talks; a face for it makes the mock interview feel
like one. Images are generated once with the course's image model and cached in the `images`
table for every user, so the whole feature costs three calls, not one per session.
"""

from __future__ import annotations

import io

from interview_app.guard import GuardPipeline
from interview_app.llm.client import ImageResult
from interview_app.storage.store import Store

AVATAR_PX = 384
PERSONA_FALLBACK = {"strict": "🧐", "neutral": "😐", "friendly": "😊"}

_BASE = (
    "A professional portrait illustration of a software engineering interviewer for an "
    "interview-practice app, head and shoulders, facing the viewer, plain soft lavender studio "
    "background, flat modern vector style with gentle shading, warm colours. Absolutely no text, "
    "letters, logos, labels or watermarks anywhere in the image. Square composition. "
)
# Three different people so the personas are told apart at a glance.
PERSONA_PROMPTS = {
    "strict": _BASE
    + "A woman in her fifties with short grey-streaked hair and a dark blazer. Expression: "
    "serious and exacting, slight frown, eyebrows raised a little, arms folded. The kind of "
    "senior interviewer who asks 'and what happens when that fails?'.",
    "neutral": _BASE
    + "A man in his thirties with glasses, a trimmed beard and a light blue shirt. Expression: "
    "calm, attentive, polite neutral face, hands resting together. Even-handed and "
    "professional.",
    "friendly": _BASE
    + "A young woman with curly dark hair and a mustard knitted jumper. Expression: warm open "
    "smile, relaxed posture, leaning slightly forward as if encouraging the candidate.",
}


def image_name(persona: str) -> str:
    return f"avatar_{persona}"


def get_avatar(store: Store, persona: str) -> tuple[bytes, str] | None:
    """Cached portrait, or None if it has not been generated yet."""
    return store.load_image(image_name(persona))


def generate_avatar(pipe: GuardPipeline, store: Store, persona: str) -> ImageResult:
    """Generate, shrink and cache the portrait. Raises GuardBlocked / ImageGenerationError."""
    result = pipe.image(PERSONA_PROMPTS[persona], purpose=f"avatar:{persona}")
    data, mime = shrink(result.data)
    store.save_image(image_name(persona), data, mime, result.usage.model)
    return ImageResult(data=data, mime=mime, usage=result.usage)


def shrink(data: bytes, size: int = AVATAR_PX) -> tuple[bytes, str]:
    """The model returns ~1 MB squares; a 384 px WebP (~30 KB) is plenty for a card.

    Returns the original bytes untouched if Pillow cannot read them.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size))
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=85)
            return out.getvalue(), "image/webp"
    except Exception:  # noqa: BLE001 - unknown format or a broken file: keep what we got
        return data, "image/png"

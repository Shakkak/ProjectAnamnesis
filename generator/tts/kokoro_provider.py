import random

import numpy as np

from tts.utils import word_audio_filename  # noqa: F401 — re-exported for existing callers

# Lazy pipeline cache keyed by lang_code — model loads once per session.
_PIPELINES: dict = {}

_VOICES_AMERICAN = ["af_heart", "af_bella", "am_michael", "am_fenrir"]
_VOICES_BRITISH  = ["bf_emma", "bm_george"]
_VOICES_ALL      = _VOICES_AMERICAN + _VOICES_BRITISH

_RANDOM_POOLS = {
    "random":          _VOICES_ALL,
    "random-american": _VOICES_AMERICAN,
    "random-british":  _VOICES_BRITISH,
}


def _get_pipeline(lang_code: str):
    if lang_code not in _PIPELINES:
        from kokoro import KPipeline
        _PIPELINES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPELINES[lang_code]


def generate_audio(
    text: str,
    output_path: str,
    lang: str = "en-us",
    voice: str = "af_heart",
    **kwargs,
) -> bool:
    """
    Generate an audio file using Kokoro TTS.

    Args:
        text:        Word or short phrase to speak.
        output_path: Full path for the output .mp3 file.
        lang:        'en-gb' / 'en-uk' → British English; anything else → American.
        voice:       Kokoro voice ID. Default 'af_heart' (American female).
                     Options: 'am_michael', 'bf_emma', 'bm_george'.

    Requires: pip install kokoro soundfile
    """
    try:
        import soundfile as sf

        if voice in _RANDOM_POOLS:
            voice = random.choice(_RANDOM_POOLS[voice])

        lang_code = "b" if ("gb" in lang.lower() or "uk" in lang.lower()) else "a"
        pipeline = _get_pipeline(lang_code)

        chunks = [audio for _, _, audio in pipeline(text, voice=voice)]
        if not chunks:
            return False

        sf.write(output_path, np.concatenate(chunks), samplerate=24000)
        return True

    except Exception as e:
        print(f"  kokoro error for '{text[:30]}': {e}")
        return False

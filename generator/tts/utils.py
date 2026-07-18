import re
import unicodedata


def word_audio_filename(word: str) -> str:
    """
    Deterministic human-readable filename for a word or short phrase.

    Normalises accented characters (é→e, ü→u) before slugifying so the
    filename stays ASCII and matches what the generator looks for.

    Examples:
        'agricultural'  → 'agricultural.mp3'
        'break down'    → 'break_down.mp3'
        'résumé'        → 'resume.mp3'
    """
    w = unicodedata.normalize("NFD", word)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", w.strip().lower()).strip("_")
    return f"{slug}.mp3"

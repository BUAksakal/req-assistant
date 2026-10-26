import re

VAGUE_WORDS = {"fast", "quickly", "approximately", "about", "sufficient", "adequate"}


def find_vague_words(text: str) -> list[str]:
    """Return the vague words found in a requirement text."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w in VAGUE_WORDS]

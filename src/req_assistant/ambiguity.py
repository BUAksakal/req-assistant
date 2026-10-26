VAGUE_WORDS = {"fast", "quickly", "approximately", "about", "sufficient", "adequate"}


def find_vague_words(text: str) -> list[str]:
    """Return the vague words found in a requirement text."""
    words = text.lower().split()
    return [w for w in words if w in VAGUE_WORDS]
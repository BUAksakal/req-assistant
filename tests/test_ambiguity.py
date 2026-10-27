from reqlens.ambiguity import find_vague_words


def test_finds_vague_word():
    assert find_vague_words("The system shall brake fast") == ["fast"]


def test_clear_requirement_has_no_vague_words():
    assert find_vague_words("The system shall brake within 200 ms") == []


def test_finds_vague_word_with_punctuation():
    assert find_vague_words("The system shall brake fast.") == ["fast"]

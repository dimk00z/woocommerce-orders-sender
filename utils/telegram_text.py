def split_telegram_text(text: str, limit: int = 3500):
    """Split without losing text, counting non-BMP characters as two units."""
    start = 0
    size = 0
    for index, character in enumerate(text):
        width = 2 if ord(character) > 0xFFFF else 1
        if size + width > limit:
            yield text[start:index]
            start = index
            size = 0
        size += width
    if start < len(text):
        yield text[start:]

from html import escape
from html.parser import HTMLParser


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


class _ReportParser(HTMLParser):
    """Read the report's supported markup into text with bold spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bold = False
        self.spans = []

    def handle_starttag(self, tag, attrs):
        if tag != "b" or attrs or self.bold:
            raise ValueError("Unsupported report HTML")
        self.bold = True

    def handle_endtag(self, tag):
        if tag != "b" or not self.bold:
            raise ValueError("Unbalanced report HTML")
        self.bold = False

    def handle_data(self, data):
        self.spans.append((data, self.bold))


def split_telegram_html(text: str, limit: int = 3500):
    """Split escaped report HTML, keeping each chunk's tags and entities intact."""
    if limit < 16:
        raise ValueError("HTML chunk limit must be at least 16")
    parser = _ReportParser()
    parser.feed(text)
    parser.close()
    if parser.bold:
        raise ValueError("Unclosed report HTML")
    chunk = []
    size = 0
    bold = False
    for data, wanted_bold in parser.spans:
        for character in data:
            encoded = escape(character, quote=False)
            width = len(encoded.encode("utf-16-le")) // 2
            transition = (
                ("<b>" if wanted_bold else "</b>") if bold != wanted_bold else ""
            )
            if size + len(transition) + width + (4 if wanted_bold else 0) > limit:
                yield "".join(chunk) + ("</b>" if bold else "")
                chunk = []
                size = 0
                bold = False
                transition = "<b>" if wanted_bold else ""
            chunk.extend((transition, encoded))
            size += len(transition) + width
            bold = wanted_bold
    if chunk:
        yield "".join(chunk) + ("</b>" if bold else "")

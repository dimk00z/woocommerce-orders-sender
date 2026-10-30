import unittest
from html.parser import HTMLParser

from utils import telegram_text


class ParsedText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bold = False
        self.characters = []

    def handle_starttag(self, tag, attrs):
        assert tag == "b" and not self.bold
        self.bold = True

    def handle_endtag(self, tag):
        assert tag == "b" and self.bold
        self.bold = False

    def handle_data(self, data):
        self.characters.extend((character, self.bold) for character in data)


class HTMLSplitTests(unittest.TestCase):
    def test_long_report_keeps_text_and_bold_across_chunks(self):
        source = (
            "Заголовок\n<b>"
            + "Товар &amp; &lt;курс&gt; 😀" * 600
            + "</b>\n\n<b>Итого: 19900.0 руб.</b>"
        )
        expected = ParsedText()
        expected.feed(source)
        actual = []
        chunks = list(telegram_text.split_telegram_html(source))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-16-le")) // 2, 3500)
            parsed = ParsedText()
            parsed.feed(chunk)
            self.assertFalse(parsed.bold)
            actual.extend(parsed.characters)
        self.assertEqual(actual, expected.characters)

    def test_plain_text_and_empty_report(self):
        self.assertEqual(list(telegram_text.split_telegram_html("")), [])
        self.assertEqual(
            list(telegram_text.split_telegram_html("a &amp; b")), ["a &amp; b"]
        )

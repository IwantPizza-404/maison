from apps.core import telegram


def test_url_buttons_skip_localhost():
    assert telegram.url_buttons(("Сайт", "http://localhost:3000")) is None
    markup = telegram.url_buttons(
        ("Сайт", "http://127.0.0.1:3000"), ("Часы", "https://maison.uz/watches/x")
    )
    assert markup == {"inline_keyboard": [[{"text": "Часы", "url": "https://maison.uz/watches/x"}]]}

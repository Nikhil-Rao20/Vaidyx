"""Tumour Board theme (V1 item 1.9): self-hosted open-licence fonts, text colours at 4.5:1 or better on white, no em dashes, and
the UI test's viewport option."""
import os, re

import pytest

from tumour_board.eval import contrast_check

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
TB = os.path.join(ROOT, "static", "tb")
CSS = open(os.path.join(TB, "tb.css"), encoding="utf-8").read()
HTML = open(os.path.join(TB, "index.html"), encoding="utf-8").read()


def test_text_tokens_meet_contrast():
    lines, fails = contrast_check.check(CSS)
    assert not fails, fails
    assert contrast_check.ratio(contrast_check.root_tokens(CSS)["body"], "#ffffff") >= 4.5


def test_contrast_check_flags_low_contrast_and_missing_tokens():
    weak = re.sub(r"--muted:\s*#[0-9a-fA-F]+", "--muted: #9aa5b1", CSS, count=1)
    assert any("--muted" in f for f in contrast_check.check(weak)[1])
    assert contrast_check.check(":root { --ink: #000; }")[1][0].startswith("missing tokens")
    assert round(contrast_check.ratio("#000", "#fff"), 1) == 21.0
    assert abs(contrast_check.ratio("#046483", "#ffffff") - 6.6) < 0.1


def test_fonts_are_self_hosted_woff2_with_licences():
    urls = re.findall(r"url\((/static/tb/fonts/[^)]+)\)", CSS)
    assert any("AtkinsonHyperlegible" in u for u in urls) and any("JetBrainsMono" in u for u in urls)
    for u in urls:
        with open(os.path.join(ROOT, u.lstrip("/")), "rb") as f:
            assert f.read(4) == b"wOF2", u
    fonts = os.path.join(TB, "fonts")
    for lic in ("OFL-AtkinsonHyperlegible.txt", "OFL-JetBrainsMono.txt"):
        assert "SIL Open Font License" in open(os.path.join(fonts, lic), encoding="utf-8").read()
    assert not re.search(r"https?://", " ".join(re.findall(r"url\(([^)]*)\)", CSS)))  # nothing remote: works offline
    for href in re.findall(r'<link rel="preload" href="([^"]+)"', HTML):
        assert os.path.exists(os.path.join(ROOT, href.lstrip("/")))


def test_primary_is_never_a_text_colour():
    assert not re.search(r"(?<![-\w])color:\s*var\(--primary\)", CSS)
    assert "color: var(--on-primary)" in CSS


def test_no_em_dashes():
    for name in os.listdir(TB) + [os.path.join("fonts", n) for n in os.listdir(os.path.join(TB, "fonts"))]:
        p = os.path.join(TB, name)
        if os.path.isfile(p) and name.endswith((".css", ".html", ".md")):
            text = open(p, encoding="utf-8").read()
            assert "\u2014" not in text, name  # no em dashes in UI files


def test_light_top_bar_uses_dark_wordmark():
    assert "/static/vaidyx-wordmark.svg" in HTML and "wordmark-white" not in HTML
    assert os.path.exists(os.path.join(ROOT, "static", "vaidyx-wordmark.svg"))


def test_ui_test_viewports_option():
    pytest.importorskip("playwright")
    import argparse
    from tumour_board.eval import ui_test
    assert ui_test.parse_viewports("desktop,tablet, phone") == ["desktop", "tablet", "phone"]
    assert ui_test.VIEWPORTS == {"desktop": (1600, 1000), "tablet": (1024, 768), "phone": (390, 844)}
    with pytest.raises(argparse.ArgumentTypeError):
        ui_test.parse_viewports("watch")

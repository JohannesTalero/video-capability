"""Tests for brand_css generator."""

from __future__ import annotations

from pipeline.renderers.brand_css import render_brand_css


def test_brand_css_contains_all_colors():
    brand = {
        "colors": {
            "primary": "#2962FF",
            "primary_dark": "#0039CB",
            "accent": "#FF6D00",
            "accent_dark": "#C43E00",
            "carbon": "#212121",
            "carbon_light": "#484848",
            "surface": "#FFFFFF",
            "background": "#F5F5F5",
        },
    }
    css = render_brand_css(brand)
    assert "--primary: #2962FF;" in css
    assert "--accent: #FF6D00;" in css
    assert "--carbon: #212121;" in css
    assert "--surface: #FFFFFF;" in css


def test_brand_css_starts_with_root_selector():
    brand = {
        "colors": {
            "primary": "#000",
            "primary_dark": "#000",
            "accent": "#000",
            "accent_dark": "#000",
            "carbon": "#000",
            "carbon_light": "#000",
            "surface": "#fff",
            "background": "#fff",
        }
    }
    css = render_brand_css(brand)
    assert css.startswith(":root {")
    assert css.rstrip().endswith("}")


def test_brand_css_deterministic():
    brand = {
        "colors": {
            "primary": "#2962FF",
            "primary_dark": "#0039CB",
            "accent": "#FF6D00",
            "accent_dark": "#C43E00",
            "carbon": "#212121",
            "carbon_light": "#484848",
            "surface": "#FFFFFF",
            "background": "#F5F5F5",
        }
    }
    assert render_brand_css(brand) == render_brand_css(brand)

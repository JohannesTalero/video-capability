"""Generate brand.css from brand.json. Pure function, deterministic."""

from __future__ import annotations


def render_brand_css(brand: dict) -> str:
    c = brand["colors"]
    return (
        ":root {\n"
        f"  --primary: {c['primary']};\n"
        f"  --primary-dark: {c['primary_dark']};\n"
        f"  --accent: {c['accent']};\n"
        f"  --accent-dark: {c['accent_dark']};\n"
        f"  --carbon: {c['carbon']};\n"
        f"  --carbon-light: {c['carbon_light']};\n"
        f"  --surface: {c['surface']};\n"
        f"  --background: {c['background']};\n"
        "}\n"
    )

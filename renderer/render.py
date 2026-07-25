#!/usr/bin/env python3
"""Render an infographic PNG from a content dict.

Usage (CLI):
    python renderer/render.py                  # renders sample content
    python renderer/render.py out.png          # custom output path

Usage (module):
    from renderer.render import render
    png_path = render(content_dict, "renderer/output/infographic.png")
"""
import sys
import pathlib
import tempfile

from jinja2 import Environment, FileSystemLoader

ROOT      = pathlib.Path(__file__).parent
TEMPLATE  = "process_infographic.html.j2"
OUTPUT    = ROOT / "output" / "infographic.png"

# Canvas size for the (currently only) template.
_CANVAS_SIZES = {
    "process_infographic.html.j2": (1080, 1330),
}


def _build_html(content: dict, template: str = TEMPLATE) -> str:
    env  = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    tmpl = env.get_template(template)
    return tmpl.render(**content)


def _draw(page) -> None:
    """Trigger JS arrow drawing + autofit after fonts are confirmed loaded."""
    page.evaluate("window.drawInfographic && window.drawInfographic()")


def render(content: dict, out_path: str, template: str = TEMPLATE, scale: int = 3) -> str:
    """Render content dict → PNG using the given template. Returns out_path string.
    scale is the device pixel ratio Playwright renders at — 3x on a 1080-wide canvas
    yields a ~3240px-wide export, crisp even at LinkedIn's full-screen tap-to-expand view."""
    from playwright.sync_api import sync_playwright

    html = _build_html(content, template)
    width, height = _CANVAS_SIZES.get(template, (1080, 1350))

    # Write HTML to temp file so file:// URL works for relative asset loading
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(html)
        tmp_html = f.name

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            page.goto(f"file://{tmp_html}")
            page.wait_for_load_state("networkidle")   # waits for Google Fonts
            page.wait_for_timeout(800)                # extra buffer for font apply
            _draw(page)                               # draw arrows from real positions
            page.wait_for_timeout(150)                # let SVG paint
            el = page.query_selector(".page")
            el.screenshot(path=str(out_path))
            browser.close()
    finally:
        import os
        os.unlink(tmp_html)

    print(f"  [render] → {out_path}")
    return str(out_path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(OUTPUT)
    sample = {
        "title_line1": "Why Your Agent",
        "title_line2": "Breaks In Prod",
        "tagline": "From clean demo to production reality.",
        "hook": "demos never see concurrent load or a missing fallback path.",
        "stages": [
            {"label": "The Demo", "snippet": "status: ok"},
            {"label": "Real Traffic", "snippet": "load += 10x"},
            {"label": "It Breaks", "snippet": "ERROR: timeout"},
        ],
        "steps": [
            {"label": "The Demo", "points": ["Static input", "Happy path", "Controlled data"]},
            {"label": "Real Traffic", "points": ["Dynamic input", "Edge cases", "Concurrent load"]},
            {"label": "Root Cause", "points": ["No validation", "Brittle logic", "No fallback"]},
            {"label": "The Fix", "points": ["Guardrails", "Observability", "Retry logic"]},
        ],
        "flow_a_items": ["Demo", "Real Traffic", "No Validation", "Silent Failure", "Guardrails", "Stable"],
        "flow_b_items": ["Works Alone", "Breaks Live", "Add Guardrails", "Works Live"],
    }
    render(sample, out)
    print(f"Saved to {out}")

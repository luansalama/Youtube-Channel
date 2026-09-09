from __future__ import annotations

import html
import json
from pathlib import Path

from .core import StudioError, load_project


def _safe(text: str) -> str:
    return html.escape(text or "", quote=True)


def generate_thumbnail_wireframes(root: Path, slug: str) -> list[Path]:
    video_dir, project = load_project(root, slug)
    source = video_dir / ".studio" / "internal" / "release" / "thumbnail-concepts.json"
    if not source.is_file():
        raise StudioError(f"Missing thumbnail concept file: {source}")
    try:
        concepts = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StudioError(f"Invalid thumbnail concepts JSON: {exc}") from exc
    if isinstance(concepts, dict):
        concepts = concepts.get("concepts", [])
    if not isinstance(concepts, list) or not concepts:
        raise StudioError("thumbnail-concepts.json must contain a non-empty concepts list.")
    output_dir = video_dir / ".studio" / "internal" / "release" / "wireframes"
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, concept in enumerate(concepts, start=1):
        headline = _safe(str(concept.get("headline", "NO TEXT")))
        subject = _safe(str(concept.get("subject") or concept.get("name") or "Primary subject"))
        secondary = _safe(str(concept.get("secondary") or concept.get("secondary_shape") or "Environmental clue"))
        composition = _safe(str(concept.get("composition") or f"focal {concept.get('focal_shape', 'unspecified')}"))
        emotion = _safe(str(concept.get("emotion") or concept.get("note") or "Describe emotion"))
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#151515"/>
  <rect x="48" y="48" width="1184" height="624" rx="14" fill="none" stroke="#777" stroke-width="3" stroke-dasharray="14 10"/>
  <rect x="70" y="90" width="520" height="500" rx="22" fill="#2b2b2b" stroke="#d7d7d7" stroke-width="4"/>
  <text x="330" y="320" text-anchor="middle" fill="#f2f2f2" font-family="Arial" font-size="42" font-weight="700">{subject}</text>
  <text x="330" y="375" text-anchor="middle" fill="#bdbdbd" font-family="Arial" font-size="25">{emotion}</text>
  <path d="M650 175 L1170 175 L1170 520 L650 520 Z" fill="#202020" stroke="#a0a0a0" stroke-width="4"/>
  <text x="910" y="330" text-anchor="middle" fill="#f0f0f0" font-family="Arial" font-size="34">{secondary}</text>
  <rect x="610" y="535" width="590" height="112" rx="14" fill="#eeeeee"/>
  <text x="905" y="606" text-anchor="middle" fill="#111111" font-family="Arial" font-size="52" font-weight="900">{headline}</text>
  <text x="72" y="696" fill="#aaaaaa" font-family="Arial" font-size="18">Wireframe {index} — {project['title']} — composition: {composition}</text>
</svg>'''
        output = output_dir / f"concept-{index:02d}.svg"
        output.write_text(svg, encoding="utf-8", newline="\n")
        outputs.append(output)
    return outputs

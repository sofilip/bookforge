"""
EPUB builder for BookForge.

Generates a Markdown intermediate file and compiles it to EPUB
using Pandoc, with embedded fonts, custom CSS, and cover image.
"""

import re
import sys
import subprocess
import shutil
from pathlib import Path

import fitz  # PyMuPDF

from .config import BookConfig


# Default EPUB CSS (bundled)
_DEFAULT_CSS = """\
body {
  font-family: 'GFSDidot', 'EB Garamond', Georgia, 'Times New Roman', serif;
  line-height: 1.55;
  text-align: justify;
  margin: 5% 8%;
  color: #1a1a1a;
  background-color: #fafafa;
}

h1 {
  text-align: center;
  font-size: 1.8em;
  letter-spacing: 0.08em;
  margin-top: 2em;
  margin-bottom: 0.3em;
  font-weight: normal;
  text-transform: uppercase;
}

h2 {
  text-align: center;
  font-size: 1.3em;
  letter-spacing: 0.05em;
  margin-top: 0.3em;
  margin-bottom: 2em;
  font-weight: normal;
  color: #333;
}

p {
  text-indent: 1.8em;
  margin-top: 0;
  margin-bottom: 0;
  text-align: justify;
  hyphens: auto;
  -webkit-hyphens: auto;
}

p.first-p {
  text-indent: 0;
}

.dropcap {
  float: left;
  font-size: 3.4em;
  line-height: 0.8;
  margin: 0.1em 0.15em 0 0;
  font-weight: bold;
}

.colophon {
  text-align: center;
  font-size: 0.9em;
  line-height: 1.6;
  margin: 4em auto 3em auto;
  padding: 1.5em;
  border-top: 1px solid #ccc;
  border-bottom: 1px solid #ccc;
  max-width: 80%;
  color: #444;
}

.ornament {
  text-align: center;
  margin: 3em auto;
  font-size: 1.1em;
  letter-spacing: 0.1em;
  color: #555;
}
"""


def generate_markdown(
    config: BookConfig,
    all_parts_data: list[dict],
) -> str:
    """
    Generate Pandoc-compatible Markdown with YAML front matter.

    *all_parts_data* has the same structure as in typesetter.generate_latex.
    """
    lines = [
        "---",
        f'title: "{config.title}"',
    ]
    if config.subtitle:
        lines.append(f'subtitle: "{config.subtitle}"')
    lines.extend([
        f'author: "{config.author}"',
        f'lang: "{config.language}"',
    ])
    if config.translator:
        lines.append(f'translator: "{config.translator}"')
    if config.description:
        lines.append(f'description: "{config.description}"')
    lines.extend([
        f'publisher: "{config.publisher}"',
        f'date: "{config.year}"',
        "---",
        "",
    ])

    for part_item in all_parts_data:
        meta = part_item["metadata"]
        sections = part_item["sections"]
        p_name = meta.get("name", "")
        p_title = meta.get("title", "")
        dropcap_char = meta.get("dropcap_char", "")

        lines.append(f"# {p_name}: {p_title}")
        lines.append("")

        for sec_num in sorted(sections.keys()):
            lines.append(f"## {p_name} — Section {sec_num}")
            lines.append("")

            raw_sec = sections[sec_num]
            paras = re.split(r"\n\s*\n", raw_sec)

            for p_idx, p in enumerate(paras):
                p_clean = p.replace("\n", " ").strip()
                if not p_clean:
                    continue
                if (
                    config.dropcap
                    and sec_num == 1
                    and p_idx == 0
                    and dropcap_char
                    and p_clean.startswith(dropcap_char)
                ):
                    rest = p_clean[len(dropcap_char):]
                    lines.append(
                        f'<p class="first-p">'
                        f'<span class="dropcap">{dropcap_char}</span>'
                        f"{rest}</p>"
                    )
                else:
                    lines.append(f"<p>{p_clean}</p>")
                lines.append("")

        lines.extend([
            '<div class="ornament">',
            "",
            "\u2014 \u2766 \u2014",
            "",
            f"**END OF {p_name.upper()}**",
            "",
            "</div>",
            "",
        ])

    lines.extend([
        '<div class="ornament">',
        "",
        "\u2726 \u2726 \u2726",
        "",
        "**END OF BOOK**",
        "",
        "</div>",
        "",
    ])

    return "\n".join(lines)


def extract_cover(pdf_path: Path, output_path: Path, dpi: int = 200) -> Path:
    """Render the first page of a PDF as a cover image."""
    doc = fitz.open(str(pdf_path))
    pix = doc[0].get_pixmap(dpi=dpi)
    pix.save(str(output_path))
    doc.close()
    return output_path


def compile_epub(
    md_path: Path,
    output_path: Path,
    css_path: Path | None = None,
    cover_path: Path | None = None,
    font_path: Path | None = None,
) -> Path:
    """
    Compile Markdown to EPUB using Pandoc.
    Returns the path to the generated EPUB.
    """
    if not shutil.which("pandoc"):
        print(
            "Error: pandoc not found. Install it with your package manager.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Write default CSS if none provided
    if css_path is None:
        css_path = md_path.parent / "epub_style.css"
        if not css_path.exists():
            css_path.write_text(_DEFAULT_CSS, encoding="utf-8")

    cmd = [
        "pandoc",
        str(md_path),
        "-o", str(output_path),
        "--toc",
        "--toc-depth=2",
    ]

    if css_path and css_path.exists():
        cmd.extend(["--css", str(css_path)])
    if cover_path and cover_path.exists():
        cmd.extend(["--epub-cover-image", str(cover_path)])
    if font_path and font_path.exists():
        cmd.extend(["--epub-embed-font", str(font_path)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error during Pandoc EPUB compilation:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    return output_path


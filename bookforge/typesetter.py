"""
XeLaTeX typesetter for BookForge.

Generates a complete XeLaTeX document from extracted and audited text,
then compiles it into a publisher-grade PDF.  The template is
configurable for language, font, paper size, and structure.
"""

import re
import sys
import subprocess
import shutil
from pathlib import Path

from .config import BookConfig


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in body text."""
    text = text.replace("\\", "\\textbackslash{}")
    for ch, esc in [
        ("&", "\\&"), ("%", "\\%"), ("$", "\\$"),
        ("#", "\\#"), ("_", "\\_"), ("~", "\\textasciitilde{}"),
    ]:
        text = text.replace(ch, esc)
    return text


def _polyglossia_lang(lang_code: str) -> str:
    """Map a language code to a Polyglossia language name."""
    mapping = {
        "el": "greek",
        "grc": "greek",
        "en": "english",
        "fr": "french",
        "de": "german",
        "it": "italian",
        "es": "spanish",
        "pt": "portuguese",
        "ru": "russian",
    }
    return mapping.get(lang_code, "english")


def _paper_geometry(paper: str) -> str:
    """Return geometry settings for the given paper size."""
    presets = {
        "a5": (
            "paperwidth=148mm, paperheight=210mm, "
            "top=22mm, bottom=22mm, inner=22mm, outer=18mm, "
            "bindingoffset=2mm, headheight=14pt, footskip=12mm"
        ),
        "a4": (
            "paperwidth=210mm, paperheight=297mm, "
            "top=25mm, bottom=25mm, inner=25mm, outer=20mm, "
            "headheight=14pt, footskip=14mm"
        ),
        "letter": (
            "paperwidth=8.5in, paperheight=11in, "
            "top=1in, bottom=1in, inner=1in, outer=0.8in, "
            "headheight=14pt, footskip=14mm"
        ),
    }
    return presets.get(paper.lower(), presets["a5"])


def generate_latex(
    config: BookConfig,
    all_parts_data: list[dict],
) -> str:
    """
    Generate a complete XeLaTeX document string.

    *all_parts_data* is a list of dicts, each with:
      - 'metadata': a part dict from config.parts
      - 'sections': dict mapping section_num -> text
    """
    poly_lang = _polyglossia_lang(config.language)
    geom = _paper_geometry(config.paper)
    font = config.font

    # Build body
    body_parts = []
    for part_item in all_parts_data:
        meta = part_item["metadata"]
        sections = part_item["sections"]
        p_name = meta.get("name", "")
        p_title = meta.get("title", "")
        dropcap_char = meta.get("dropcap_char", "")

        part_header = "\n".join([
            "",
            "\\cleardoublepage",
            "\\thispagestyle{empty}",
            "\\vspace*{4cm}",
            "\\begin{center}",
            "{\\Large\\textsc{" + p_name + "}}\\\\[1em]",
            "{\\huge\\textbf{" + p_title + "}}\\\\[1.5em]",
            "\\rule{4cm}{0.5pt}",
            "\\end{center}",
            "\\addcontentsline{toc}{part}{" + p_name + ": " + p_title + "}",
            "\\cleardoublepage",
            "",
        ])

        sec_blocks = []
        for sec_num in sorted(sections.keys()):
            raw_sec = sections[sec_num]
            paras = re.split(r"\n\s*\n", raw_sec)
            clean = []
            for p_idx, p in enumerate(paras):
                p_str = p.replace("\n", " ").strip()
                if not p_str:
                    continue
                p_esc = _escape_latex(p_str)

                # Drop cap on first paragraph of section 1
                if (
                    config.dropcap
                    and sec_num == 1
                    and p_idx == 0
                    and dropcap_char
                    and p_esc.startswith(dropcap_char)
                ):
                    rest = p_esc[len(dropcap_char):]
                    if rest.startswith(" "):
                        rest = rest[1:]
                    p_esc = (
                        "\\lettrine[lines=3, lhang=0.1, nindent=0.1em]"
                        "{\\textbf{" + dropcap_char + "}}{}"
                        + rest
                    )
                clean.append(p_esc)

            sec_body = "\n\n".join(clean)
            sec_blocks.append(
                "\\clearpage\n"
                "\\section*{" + str(sec_num) + "}\n\n" + sec_body
            )

        separator = (
            "\n\n\\vspace{1.5em}"
            "\\begin{center}\\rule{2cm}{0.4pt}\\end{center}"
            "\\vspace{1.5em}\n\n"
        )
        part_body = separator.join(sec_blocks)
        body_parts.append(part_header + "\n" + part_body)

    full_body = "\n\n".join(body_parts)

    # Translator line for cover
    translator_line = ""
    if config.translator:
        translator_line = (
            "{\\normalsize " + config.translator + "}\\\\[1.8cm]\n"
        )

    # Assemble document
    latex = (
        "\\documentclass[11pt," + config.paper + "paper,twoside,openright]{book}\n"
        "\n"
        "\\usepackage{fontspec}\n"
        "\\usepackage{polyglossia}\n"
        "\\setmainlanguage{" + poly_lang + "}\n"
        "\n"
        "\\setmainfont{" + font + "}[\n"
        "    Ligatures=TeX,\n"
        "    Numbers=OldStyle\n"
        "]\n"
        "\n"
        "\\usepackage{geometry}\n"
        "\\geometry{" + geom + "}\n"
        "\n"
        "\\usepackage{fancyhdr}\n"
        "\\usepackage{setspace}\n"
        "\\setstretch{1.22}\n"
        "\n"
        "\\usepackage{lettrine}\n"
        "\\usepackage{titlesec}\n"
        "\\usepackage{microtype}\n"
        "\\usepackage{tocloft}\n"
        "\\usepackage{hyperref}\n"
        "\n"
        "% Hyphenation & line breaking\n"
        "\\emergencystretch=3em\n"
        "\\tolerance=2000\n"
        "\\hbadness=2000\n"
        "\n"
        "\\hypersetup{\n"
        "    colorlinks=false,\n"
        "    pdfborder={0 0 0},\n"
        "    pdftitle={" + config.title + "},\n"
        "    pdfauthor={" + config.author + "},\n"
        "}\n"
        "\n"
        "\\titleformat{\\section}[block]\n"
        "  {\\Large\\bfseries\\filcenter}\n"
        "  {}\n"
        "  {0pt}\n"
        "  {}\n"
        "\\titlespacing*{\\section}{0pt}{2em}{1.5em}\n"
        "\n"
        "\\renewcommand{\\cftpartleader}{\\cftdotfill{\\cftdotsep}}\n"
        "\\renewcommand{\\cftpartfont}{\\bfseries}\n"
        "\n"
        "\\setlength{\\parindent}{1.6em}\n"
        "\\setlength{\\parskip}{0pt}\n"
        "\n"
        "\\pagestyle{fancy}\n"
        "\\fancyhf{}\n"
        "\\fancyhead[LE]{\\small\\textsc{" + config.author + "}}\n"
        "\\fancyhead[RO]{\\small\\textsc{" + config.title + "}}\n"
        "\\fancyfoot[C]{\\small\\thepage}\n"
        "\\renewcommand{\\headrulewidth}{0.3pt}\n"
        "\\renewcommand{\\footrulewidth}{0pt}\n"
        "\n"
        "\\fancypagestyle{plain}{\n"
        "    \\fancyhf{}\n"
        "    \\fancyfoot[C]{\\small\\thepage}\n"
        "    \\renewcommand{\\headrulewidth}{0pt}\n"
        "}\n"
        "\n"
        "\\begin{document}\n"
        "\n"
        "% Cover page\n"
        "\\begin{titlepage}\n"
        "\\thispagestyle{empty}\n"
        "\\begin{center}\n"
        "\\vspace*{1.2cm}\n"
        "\n"
        "{\\Huge\\textsc{" + config.author + "}}\\\\[2.2cm]\n"
        "\n"
        "\\rule{0.8\\textwidth}{1.5pt}\\\\[0.4cm]\n"
        "{\\fontsize{24}{28}\\selectfont\\textbf{" + config.title.upper() + "}}\\\\[0.6cm]\n"
        "\\rule{0.8\\textwidth}{1.5pt}\\\\[1.8cm]\n"
        "\n"
        "\\vfill\n"
        "\n"
        + translator_line +
        "{\\small\\textsc{" + config.publisher + " \\textbullet{} " + config.year + "}}\n"
        "\\vspace*{0.8cm}\n"
        "\\end{center}\n"
        "\\end{titlepage}\n"
        "\n"
        "\\cleardoublepage\n"
        "\\thispagestyle{plain}\n"
        "\\setcounter{tocdepth}{-1}\n"
        "\\tableofcontents\n"
        "\n"
        + full_body +
        "\n"
        "\n"
        "\\vspace{3em}\n"
        "\\begin{center}\n"
        "\\rule{3cm}{0.4pt}\\\\[1em]\n"
        "{\\large\\textsc{End of Book}}\\\\[0.5em]\n"
        "\\rule{3cm}{0.4pt}\n"
        "\\end{center}\n"
        "\n"
        "\\end{document}\n"
    )
    return latex


def compile_pdf(
    tex_path: Path,
    output_dir: Path | None = None,
    passes: int = 2,
) -> Path:
    """
    Compile a .tex file to PDF using XeLaTeX.
    Returns the path to the generated PDF.
    """
    if not shutil.which("xelatex"):
        print("Error: xelatex not found. Install TeX Live.", file=sys.stderr)
        sys.exit(1)

    work_dir = tex_path.parent
    for i in range(passes):
        label = f"Pass {i + 1}/{passes}"
        print(f"  XeLaTeX {label}...")
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", tex_path.name],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error during XeLaTeX {label}:", file=sys.stderr)
            print(result.stdout[-1500:], file=sys.stderr)
            sys.exit(1)

    pdf_path = tex_path.with_suffix(".pdf")
    if output_dir and output_dir != work_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / pdf_path.name
        shutil.move(str(pdf_path), str(dest))
        pdf_path = dest

    return pdf_path


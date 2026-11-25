"""
BookForge CLI — Command-line interface for the universal book publishing pipeline.

Usage:
    bookforge extract --pdf INPUT.pdf --config book.toml --output text/
    bookforge audit   --input text/ --config book.toml --output audited/
    bookforge publish --input audited/ --config book.toml --format pdf,epub,txt
    bookforge run     --pdf INPUT.pdf --config book.toml --format pdf,epub,txt
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from . import __version__
from .config import BookConfig
from .extractor import extract_part
from .auditor import SecondAuditor
from .typesetter import generate_latex, compile_pdf
from .epub_builder import generate_markdown, compile_epub, extract_cover


def _slug(title: str) -> str:
    """Create a filesystem-safe slug from a title."""
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_title = nfkd.encode("ascii", "ignore").decode("ascii")
    if not ascii_title:
        ascii_title = "book"
    slug = re.sub(r"[^\w\s-]", "", ascii_title).strip().lower()
    return re.sub(r"[-\s]+", "_", slug) or "book"


def _cmd_extract(args):
    """Extract text from PDF based on config."""
    config = BookConfig(args.config)
    pdf = Path(args.pdf).resolve()
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting from: {pdf.name}")
    print(f"Parts defined: {len(config.parts)}")

    all_parts = []
    for part in config.parts:
        print(
            f"  Part {part['num']}: {part['name']} "
            f"(pages {part['start_page']}-{part['end_page']})"
        )
        result = extract_part(
            pdf,
            part["start_page"],
            part["end_page"],
            part.get("sections", 0),
            config.section_style,
        )
        # Save raw text
        raw_file = outdir / f"part_{part['num']:02d}_raw.txt"
        raw_file.write_text(result["raw"], encoding="utf-8")

        # Save individual sections
        for sec_num, sec_text in sorted(result["sections"].items()):
            sec_file = outdir / f"part_{part['num']:02d}_sec_{sec_num:03d}.txt"
            sec_file.write_text(sec_text, encoding="utf-8")

        all_parts.append({"metadata": part, "sections": result["sections"]})

    total_secs = sum(len(p["sections"]) for p in all_parts)
    print(f"\nExtracted {len(all_parts)} parts, {total_secs} sections total.")
    print(f"Output directory: {outdir}")


def _cmd_audit(args):
    """Run the Second Auditor on extracted text."""
    config = BookConfig(args.config)
    indir = Path(args.input)
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    auditor = SecondAuditor(
        dictionary_path=config.dictionary_path,
        language=config.auditor_language,
    )

    print("Running The Second Auditor...")
    for txt_file in sorted(indir.glob("*.txt")):
        raw = txt_file.read_text(encoding="utf-8")
        audited, _ = auditor.audit_text(raw)
        (outdir / txt_file.name).write_text(audited, encoding="utf-8")

    # Reports
    report_md = outdir / "audit_report.md"
    auditor.generate_report_md(report_md, title=f"Audit Report: {config.title}")
    report_json = outdir / "audit_report.json"
    auditor.generate_report_json(report_json)

    print(f"Corrections applied: {auditor.total_corrections}")
    print(f"Reports saved to: {outdir}")


def _cmd_publish(args):
    """Typeset audited text into PDF, EPUB, and/or TXT."""
    config = BookConfig(args.config)
    indir = Path(args.input)
    outdir = Path(config.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    formats = [f.strip().lower() for f in args.format.split(",")]

    # Reconstruct parts data from files
    all_parts = []
    for part in config.parts:
        sections = {}
        for sec_file in sorted(
            indir.glob(f"part_{part['num']:02d}_sec_*.txt")
        ):
            sec_num = int(sec_file.stem.split("_")[-1])
            sections[sec_num] = sec_file.read_text(encoding="utf-8")

        if not sections:
            # Try loading from raw file
            raw_file = indir / f"part_{part['num']:02d}_raw.txt"
            if raw_file.exists():
                sections[1] = raw_file.read_text(encoding="utf-8")

        all_parts.append({"metadata": part, "sections": sections})

    slug = _slug(config.title)

    # PDF
    if "pdf" in formats:
        print("\nGenerating PDF...")
        tex_code = generate_latex(config, all_parts)
        tex_file = outdir / f"{slug}.tex"
        tex_file.write_text(tex_code, encoding="utf-8")
        pdf_path = compile_pdf(tex_file, outdir)
        print(
            f"  PDF: {pdf_path.name} "
            f"({pdf_path.stat().st_size / (1024*1024):.2f} MB)"
        )

    # TXT
    if "txt" in formats:
        print("\nGenerating plain text...")
        txt_lines = [
            config.title,
            f"Author: {config.author}",
            "=" * 60,
            "",
        ]
        for part_item in all_parts:
            meta = part_item["metadata"]
            txt_lines.append(f"\n{'=' * 60}")
            txt_lines.append(f"{meta['name']}: {meta.get('title', '')}")
            txt_lines.append(f"{'=' * 60}\n")
            for sec_num in sorted(part_item["sections"].keys()):
                txt_lines.append(f"\n--- Section {sec_num} ---\n")
                txt_lines.append(part_item["sections"][sec_num])
        txt_file = outdir / f"{slug}.txt"
        txt_file.write_text("\n".join(txt_lines), encoding="utf-8")
        print(
            f"  TXT: {txt_file.name} "
            f"({txt_file.stat().st_size / 1024:.1f} KB)"
        )

    # EPUB
    if "epub" in formats:
        print("\nGenerating EPUB...")
        md_content = generate_markdown(config, all_parts)
        md_file = outdir / f"{slug}.md"
        md_file.write_text(md_content, encoding="utf-8")

        # Cover image
        cover_path = None
        pdf_candidate = outdir / f"{slug}.pdf"
        if pdf_candidate.exists():
            cover_path = outdir / "cover.jpg"
            extract_cover(pdf_candidate, cover_path)

        # Font
        font_path = None
        for candidate in [
            Path("/usr/share/fonts/opentype/didot/GFSDidot.otf"),
            Path("/usr/share/fonts/truetype/gfs-didot/GFSDidot.otf"),
        ]:
            if candidate.exists():
                font_path = candidate
                break

        epub_path = outdir / f"{slug}.epub"
        compile_epub(
            md_file, epub_path, cover_path=cover_path, font_path=font_path
        )
        print(
            f"  EPUB: {epub_path.name} "
            f"({epub_path.stat().st_size / 1024:.1f} KB)"
        )

    print("\nPublishing complete!")


def _cmd_run(args):
    """Run the full pipeline: extract -> audit -> publish."""
    config = BookConfig(args.config)
    pdf = Path(args.pdf).resolve()
    outdir = Path(config.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    formats = [f.strip().lower() for f in args.format.split(",")]

    print("=" * 60)
    print(f"  BOOKFORGE: {config.title}")
    print(f"  Author: {config.author}")
    print("=" * 60)

    # 1. Extract
    print("\n1. Extracting text from PDF...")
    all_parts_raw = []
    for part in config.parts:
        print(
            f"   Part {part['num']}: {part['name']} "
            f"(pages {part['start_page']}-{part['end_page']})"
        )
        result = extract_part(
            pdf,
            part["start_page"],
            part["end_page"],
            part.get("sections", 0),
            config.section_style,
        )
        all_parts_raw.append({"metadata": part, "sections": result["sections"]})

    total_secs = sum(len(p["sections"]) for p in all_parts_raw)
    print(f"   Extracted {len(all_parts_raw)} parts ({total_secs} sections).")

    # 2. Audit
    print("\n2. Running The Second Auditor...")
    auditor = SecondAuditor(
        dictionary_path=config.dictionary_path,
        language=config.auditor_language,
    )
    all_parts_audited = []
    for part_item in all_parts_raw:
        audited_sections = {}
        for sec_num in sorted(part_item["sections"].keys()):
            text, _ = auditor.audit_text(part_item["sections"][sec_num])
            audited_sections[sec_num] = text
        all_parts_audited.append({
            "metadata": part_item["metadata"],
            "sections": audited_sections,
        })

    print(f"   Corrections applied: {auditor.total_corrections}")

    # Save audit report
    report_md = outdir / "audit_report.md"
    auditor.generate_report_md(
        report_md, title=f"Audit Report: {config.title}"
    )
    report_json = outdir / "audit_report.json"
    auditor.generate_report_json(report_json)

    # 3. Publish
    slug = _slug(config.title)

    if "txt" in formats:
        print("\n3. Generating plain text...")
        txt_lines = [
            config.title,
            f"Author: {config.author}",
            "=" * 60,
            "",
        ]
        for part_item in all_parts_audited:
            meta = part_item["metadata"]
            txt_lines.append(f"\n{'=' * 60}")
            txt_lines.append(f"{meta['name']}: {meta.get('title', '')}")
            txt_lines.append(f"{'=' * 60}\n")
            for sec_num in sorted(part_item["sections"].keys()):
                txt_lines.append(f"\n--- Section {sec_num} ---\n")
                txt_lines.append(part_item["sections"][sec_num])
        txt_file = outdir / f"{slug}.txt"
        txt_file.write_text("\n".join(txt_lines), encoding="utf-8")
        print(
            f"   TXT: {txt_file.name} "
            f"({txt_file.stat().st_size / 1024:.1f} KB)"
        )

    if "pdf" in formats:
        print("\n4. Generating XeLaTeX PDF...")
        tex_code = generate_latex(config, all_parts_audited)
        tex_file = outdir / f"{slug}.tex"
        tex_file.write_text(tex_code, encoding="utf-8")
        pdf_path = compile_pdf(tex_file, outdir)
        import fitz as _fitz

        _doc = _fitz.open(str(pdf_path))
        page_count = len(_doc)
        _doc.close()
        print(
            f"   PDF: {pdf_path.name} ({page_count} pages, "
            f"{pdf_path.stat().st_size / (1024*1024):.2f} MB)"
        )

    if "epub" in formats:
        print("\n5. Generating EPUB...")
        md_content = generate_markdown(config, all_parts_audited)
        md_file = outdir / f"{slug}.md"
        md_file.write_text(md_content, encoding="utf-8")

        cover_path = None
        pdf_candidate = outdir / f"{slug}.pdf"
        if pdf_candidate.exists():
            cover_path = outdir / "cover.jpg"
            extract_cover(pdf_candidate, cover_path)

        font_path = None
        for candidate in [
            Path("/usr/share/fonts/opentype/didot/GFSDidot.otf"),
            Path("/usr/share/fonts/truetype/gfs-didot/GFSDidot.otf"),
        ]:
            if candidate.exists():
                font_path = candidate
                break

        epub_path = outdir / f"{slug}.epub"
        compile_epub(
            md_file, epub_path, cover_path=cover_path, font_path=font_path
        )
        print(
            f"   EPUB: {epub_path.name} "
            f"({epub_path.stat().st_size / 1024:.1f} KB)"
        )

    print("\n" + "=" * 60)
    print("  BOOKFORGE PIPELINE COMPLETE!")
    print(f"  Output directory: {outdir}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        prog="bookforge",
        description=(
            "BookForge — Universal automated book publishing pipeline. "
            "Extract, proofread, and typeset any PDF into publisher-grade "
            "PDF, EPUB, and plain text."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"bookforge {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline commands")

    # --- extract ---
    p_extract = subparsers.add_parser(
        "extract", help="Extract text from a PDF based on a config file"
    )
    p_extract.add_argument(
        "--pdf", required=True, help="Path to the source PDF"
    )
    p_extract.add_argument(
        "--config", required=True, help="Path to book.toml config"
    )
    p_extract.add_argument(
        "--output", default="text", help="Output directory for extracted text"
    )

    # --- audit ---
    p_audit = subparsers.add_parser(
        "audit",
        help="Run the Second Auditor proofreader on extracted text",
    )
    p_audit.add_argument(
        "--input", required=True, help="Directory with extracted .txt files"
    )
    p_audit.add_argument(
        "--config", required=True, help="Path to book.toml config"
    )
    p_audit.add_argument(
        "--output", default="audited",
        help="Output directory for audited text",
    )

    # --- publish ---
    p_publish = subparsers.add_parser(
        "publish",
        help="Typeset audited text into PDF, EPUB, and/or TXT",
    )
    p_publish.add_argument(
        "--input", required=True, help="Directory with audited .txt files"
    )
    p_publish.add_argument(
        "--config", required=True, help="Path to book.toml config"
    )
    p_publish.add_argument(
        "--format", default="pdf,epub,txt",
        help="Output formats (comma-separated)",
    )

    # --- run ---
    p_run = subparsers.add_parser(
        "run",
        help="Run the full pipeline: extract -> audit -> publish",
    )
    p_run.add_argument(
        "--pdf", required=True, help="Path to the source PDF"
    )
    p_run.add_argument(
        "--config", required=True, help="Path to book.toml config"
    )
    p_run.add_argument(
        "--format", default="pdf,epub,txt",
        help="Output formats (comma-separated)",
    )

    args = parser.parse_args()

    if args.command == "extract":
        _cmd_extract(args)
    elif args.command == "audit":
        _cmd_audit(args)
    elif args.command == "publish":
        _cmd_publish(args)
    elif args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)


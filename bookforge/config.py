"""
Configuration parser for BookForge.

Reads a TOML config file describing the book structure: metadata,
parts/chapters with page ranges, language, and auditor rule sets.
"""

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


def _parse_toml(path: Path) -> dict:
    """Parse a TOML file and return its contents as a dict."""
    if tomllib is None:
        print(
            "Error: Python 3.11+ or the 'tomli' package is required "
            "to parse TOML config files.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, "rb") as f:
        return tomllib.load(f)


class BookConfig:
    """Holds all metadata and structure for a book project."""

    def __init__(self, config_path: str | Path):
        self.path = Path(config_path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")

        raw = _parse_toml(self.path)
        book = raw.get("book", {})

        # --- Book metadata ---
        self.title: str = book.get("title", "Untitled")
        self.author: str = book.get("author", "Unknown Author")
        self.translator: str = book.get("translator", "")
        self.language: str = book.get("language", "el")
        self.publisher: str = book.get("publisher", "BookForge Edition")
        self.year: str = str(book.get("year", "2026"))
        self.description: str = book.get("description", "")
        self.font: str = book.get("font", "GFS Didot")
        self.paper: str = book.get("paper", "a5")
        self.subtitle: str = book.get("subtitle", "")
        self.original_title: str = book.get("original_title", "")
        self.dropcap: bool = book.get("dropcap", True)

        # Section numbering: "numeric" (1, 2, 3), "roman" (I, II, III), or "none"
        self.section_style: str = book.get("section_style", "numeric")

        # --- Parts ---
        self.parts: list[dict] = []
        for part in raw.get("parts", []):
            self.parts.append({
                "num": part.get("num", len(self.parts) + 1),
                "name": part.get("name", f"Part {len(self.parts) + 1}"),
                "title": part.get("title", ""),
                "start_page": part.get("start_page", 1),
                "end_page": part.get("end_page", 1),
                "sections": part.get("sections", 1),
                "dropcap_char": part.get("dropcap_char", ""),
            })

        # --- Auditor settings ---
        auditor = raw.get("auditor", {})
        self.auditor_rules_file: str = auditor.get("rules_file", "")
        self.auditor_language: str = auditor.get("language", self.language)
        self.dictionary_path: str = auditor.get("dictionary_path", "")

        # --- Output settings ---
        output = raw.get("output", {})
        self.output_dir: str = output.get("dir", "output")
        self.formats: list[str] = output.get("formats", ["pdf", "epub", "txt"])

    def __repr__(self) -> str:
        return (
            f"BookConfig(title={self.title!r}, author={self.author!r}, "
            f"parts={len(self.parts)}, language={self.language!r})"
        )


"""
The Second Auditor — Linguistic proofreading engine for BookForge.

Applies multi-pass regex-based corrections to OCR-extracted text:
  - Unicode normalization and structural hygiene
  - Known optical misrecognitions (JBIG2 artifacts, kappa/chi confusion, etc.)
  - Spacing and punctuation normalization
  - Pluggable language-specific rule sets

Each correction is logged with the original text, the replacement, and a
human-readable reason, enabling a full audit trail.
"""

import re
import json
import unicodedata
from pathlib import Path


class AuditEntry:
    """A single correction record."""

    __slots__ = ("original", "corrected", "category")

    def __init__(self, original: str, corrected: str, category: str):
        self.original = original
        self.corrected = corrected
        self.category = category

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "category": self.category,
        }


class SecondAuditor:
    """
    Multi-pass proofreading engine.

    Instantiate with an optional dictionary path (Hunspell .dic file)
    for cross-referencing valid word roots.  Call :meth:`audit_text` on
    each paragraph or section of text.
    """

    def __init__(self, dictionary_path: str = "", language: str = "el"):
        self.dictionary: set[str] = set()
        self.audit_log: list[AuditEntry] = []
        self.language = language
        if dictionary_path:
            self._load_dictionary(Path(dictionary_path))
        else:
            # Try common system paths
            for candidate in [
                Path("/usr/share/hunspell/el_GR.dic"),
                Path("/usr/share/myspell/el_GR.dic"),
            ]:
                if candidate.exists():
                    self._load_dictionary(candidate)
                    break

    # -----------------------------------------------------------------
    # Dictionary loading
    # -----------------------------------------------------------------

    def _load_dictionary(self, path: Path) -> None:
        """Load a Hunspell dictionary for word validation."""
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="iso-8859-7", errors="ignore") as f:
                for line in f:
                    w = line.strip().split("/")[0].lower()
                    if w:
                        self.dictionary.add(w)
        except Exception:
            pass

    def _to_monotonic(self, text: str) -> str:
        """Strip polytonic diacritics for dictionary lookup."""
        accents = {
            "\u0300": "\u0301",
            "\u0342": "\u0301",
            "\u0313": "",
            "\u0314": "",
            "\u0345": "",
        }
        dec = unicodedata.normalize("NFD", text)
        filt = "".join(accents.get(c, c) for c in dec)
        return unicodedata.normalize("NFC", filt).lower()

    def is_valid_word(self, word: str) -> bool:
        """Check if a word or its unaccented stem exists in the dictionary."""
        if not self.dictionary:
            return True  # no dictionary loaded, skip validation
        mono = self._to_monotonic(word)
        if mono in self.dictionary:
            return True
        stem = "".join(
            c
            for c in unicodedata.normalize("NFD", mono)
            if unicodedata.category(c) != "Mn"
        )
        return stem in self.dictionary

    # -----------------------------------------------------------------
    # Core auditing
    # -----------------------------------------------------------------

    def audit_text(self, text: str) -> tuple[str, list[AuditEntry]]:
        """
        Run multi-pass auditing on a section of text.
        Returns (audited_text, list_of_corrections).
        """
        para_logs: list[AuditEntry] = []

        def sub_log(pattern, replacement, s, reason, flags=0):
            def repl_func(match):
                orig = match.group(0)
                if callable(replacement):
                    rep = replacement(match)
                else:
                    rep = match.expand(replacement)
                if orig != rep:
                    entry = AuditEntry(orig, rep, reason)
                    para_logs.append(entry)
                    self.audit_log.append(entry)
                return rep

            return re.sub(pattern, repl_func, s, flags=flags)

        # ---- PASS 1: Unicode & Structural Hygiene ----

        # Unicode confusable characters
        text = sub_log(
            "\u00b5", "\u03bc", text,
            "Micro sign (U+00B5) replaced with Greek mu",
        )
        text = sub_log(
            "\u037e", ";", text,
            "Standardize Greek question mark / semicolon",
        )
        text = sub_log(
            "[\u00b7\u0387]", "\u00b7", text,
            "Standardize Ano Teleia",
        )
        text = sub_log(
            r"[{}]", "(", text,
            "OCR stray curly brace replaced with parenthesis",
        )

        # Stray footnote artifacts
        text = sub_log(
            r"\[\s*[0-9]+[\])]?\s*", "", text,
            "Stray bracketed footnote number removed",
        )
        text = sub_log(
            r"([,.:;\u00b7])\s*[0-9\u1fbd\u2019\"']+",
            r"\1",
            text,
            "Stray superscript footnote digits glued to punctuation",
        )

        # Spacing around punctuation
        text = sub_log(
            r"([.,:;!?\u00b7\u00bb)])([" + _GK_RANGE + r"a-zA-Z])",
            r"\1 \2",
            text,
            "Missing space after punctuation",
        )
        text = sub_log(
            r"([" + _GK_RANGE + r"a-zA-Z])([\u00ab(])",
            r"\1 \2",
            text,
            "Missing space before opening quote/parenthesis",
        )

        # Em-dash spacing
        text = sub_log(r"(\w)(---|\u2014)", r"\1 \2", text, "Space before em-dash")
        text = sub_log(r"(---|\u2014)(\w)", r"\1 \2", text, "Space after em-dash")

        # ---- PASS 2: Greek OCR optical misrecognitions ----
        if self.language in ("el", "grc", "greek"):
            greek_rules = self._get_greek_rules()
            for pattern, replacement, reason in greek_rules:
                text = sub_log(pattern, replacement, text, reason)

        # ---- PASS 3: Cleanup ----
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.:;\u00b7!\u00bb])", r"\1", text)
        text = re.sub(r"([\u00ab])\s+", r"\1", text)

        return text.strip(), para_logs

    def _get_greek_rules(self) -> list[tuple[str, str, str]]:
        """Return the default Greek OCR correction rules."""
        return [
            # Kappa / Chi confusion (most common JBIG2 artifact)
            (r"\b[\u03c7\u03a7]\u03b1\u1f76\b", "\u03ba\u03b1\u1f76",
             "Chi misread for kappa in kai"),
            (r"\b[\u03c7\u03a7]\u03b1\u03af\b", "\u03ba\u03b1\u03af",
             "Chi misread for kappa in kai"),
            (r"\b[\u03c7\u03a7]\u03c1\u03b5\u03b2\u03ac\u03c4",
             "\u03ba\u03c1\u03b5\u03b2\u03ac\u03c4",
             "Chi misread for kappa (krevati)"),
            (r"\b[\u03c7\u03a7]\u03ac\u03b8\u03b5\b", "\u03ba\u03ac\u03b8\u03b5",
             "Chi misread for kappa (kathe)"),
            (r"\b[\u03c7\u03a7]\u03b1\u03c4\u03ac\b", "\u03ba\u03b1\u03c4\u03ac",
             "Chi misread for kappa (kata)"),
            (r"\b[\u03c7\u03a7]\u03b1\u03bd\u03b5\u03af\u03c2\b",
             "\u03ba\u03b1\u03bd\u03b5\u03af\u03c2",
             "Chi misread for kappa (kaneis)"),

            # Digit 6 for beta
            (r"\b6([\u03bb\u03b2\u03b3\u03c1])", r"\u03b2\1",
             "Digit 6 misread for beta"),

            # Unaccented capital starters
            (r"\b\u039f\u03c4\u03b1\u03bd\b", "\u038c\u03c4\u03b1\u03bd",
             "Missing capital accent (Otan)"),
            (r"\b\u039f\u03c4\u03b9\b", "\u038c\u03c4\u03b9",
             "Missing capital accent (Oti)"),

            # Common missing accents
            (r"\b\u03b7\u03c4\u03b1\u03bd\b", "\u03ae\u03c4\u03b1\u03bd",
             "Missing accent (itan)"),

            # Latin/Greek confusables in body text
            (r"\bH\b", "\u0397", "Latin H misread for Greek Eta"),
        ]

    # -----------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------

    def generate_report_md(
        self, output_path: Path, title: str = "Audit Report"
    ) -> None:
        """Write a Markdown audit report."""
        lines = [
            f"# The Second Auditor: {title}",
            f"**Total Corrections:** {len(self.audit_log)}\n",
            "| # | Original | Corrected | Reason |",
            "|---|----------|-----------|--------|",
        ]
        for i, entry in enumerate(self.audit_log, 1):
            lines.append(
                f"| {i} | `{entry.original}` | "
                f"**`{entry.corrected}`** | {entry.category} |"
            )
        output_path.write_text("\n".join(lines), encoding="utf-8")

    def generate_report_json(self, output_path: Path) -> None:
        """Write a JSON audit report."""
        data = [e.to_dict() for e in self.audit_log]
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @property
    def total_corrections(self) -> int:
        return len(self.audit_log)


# Greek Unicode range shorthand for regex character classes
_GK_RANGE = r"\u0370-\u03FF\u1F00-\u1FFF\u0386-\u038A\u038C\u038E-\u03A1"


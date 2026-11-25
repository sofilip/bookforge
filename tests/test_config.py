"""Basic tests for BookForge config parsing."""

import tempfile
from pathlib import Path

from bookforge.config import BookConfig


def test_config_loads():
    """Verify that a minimal TOML config can be parsed."""
    toml_content = """
[book]
title = "Test Book"
author = "Test Author"
language = "en"

[[parts]]
num = 1
name = "Part One"
title = "Introduction"
start_page = 1
end_page = 10
sections = 3
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False
    ) as f:
        f.write(toml_content)
        f.flush()
        config = BookConfig(f.name)

    assert config.title == "Test Book"
    assert config.author == "Test Author"
    assert config.language == "en"
    assert len(config.parts) == 1
    assert config.parts[0]["name"] == "Part One"
    assert config.parts[0]["start_page"] == 1
    assert config.parts[0]["end_page"] == 10

    Path(f.name).unlink()


def test_config_defaults():
    """Verify default values when optional fields are missing."""
    toml_content = """
[book]
title = "Minimal"
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False
    ) as f:
        f.write(toml_content)
        f.flush()
        config = BookConfig(f.name)

    assert config.title == "Minimal"
    assert config.author == "Unknown Author"
    assert config.language == "el"
    assert config.font == "GFS Didot"
    assert config.paper == "a5"
    assert len(config.parts) == 0

    Path(f.name).unlink()


def test_config_repr():
    """Verify repr output."""
    toml_content = """
[book]
title = "Repr Test"
author = "Someone"
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False
    ) as f:
        f.write(toml_content)
        f.flush()
        config = BookConfig(f.name)

    r = repr(config)
    assert "Repr Test" in r
    assert "Someone" in r

    Path(f.name).unlink()


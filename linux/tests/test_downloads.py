"""Naming and placing a saved item."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lios_linux.downloads import extension_for, sanitize, save_name, unique_path

NOW = datetime(2026, 3, 4, 15, 9, 27)


def test_extension_prefers_the_recognisable_jpeg_spelling() -> None:
    assert extension_for("image/jpeg") == ".jpg"


def test_extension_reads_a_parameterised_content_type() -> None:
    assert extension_for("text/plain; charset=utf-8") == ".txt"


def test_extension_falls_back_when_the_type_is_unknown_or_absent() -> None:
    assert extension_for(None) == ".bin"
    assert extension_for("application/x-nothing-in-particular") == ".bin"


def test_extension_covers_a_type_the_table_does_not_name() -> None:
    assert extension_for("application/pdf") == ".pdf"


def test_a_senders_name_is_used_as_given() -> None:
    assert save_name(filename="Notes.pdf", content_type="application/pdf", now=NOW) == "Notes.pdf"


def test_a_nameless_item_gets_a_timestamped_typed_name() -> None:
    assert save_name(filename=None, content_type="image/png", now=NOW) == "lios-20260304-150927.png"


def test_a_nameless_untyped_item_still_gets_a_readable_stem() -> None:
    assert save_name(filename=None, content_type=None, now=NOW) == "lios-20260304-150927.bin"


def test_a_name_that_sanitises_to_nothing_falls_back() -> None:
    assert (
        save_name(filename="../", content_type="image/png", now=NOW) == "lios-20260304-150927.png"
    )


def test_sanitize_keeps_only_the_last_path_component() -> None:
    assert sanitize("../../.bashrc") == ".bashrc"
    assert sanitize("C:\\Users\\me\\report.doc") == "report.doc"


def test_sanitize_strips_control_characters() -> None:
    assert sanitize("we\x00ird\nname.txt") == "weirdname.txt"


def test_sanitize_rejects_names_with_nothing_left() -> None:
    assert sanitize("") is None
    assert sanitize("..") is None
    assert sanitize("/") is None


def test_sanitize_caps_a_long_stem_but_keeps_the_extension() -> None:
    result = sanitize("x" * 500 + ".png")
    assert result is not None
    assert result.endswith(".png")
    assert len(result) == 204


def test_unique_path_is_the_plain_one_when_nothing_is_there(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "photo.jpg") == tmp_path / "photo.jpg"


def test_unique_path_counts_up_past_what_already_exists(tmp_path: Path) -> None:
    (tmp_path / "photo.jpg").touch()
    (tmp_path / "photo (2).jpg").touch()
    assert unique_path(tmp_path, "photo.jpg") == tmp_path / "photo (3).jpg"

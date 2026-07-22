"""Page-range parsing for batch CLI."""

import pytest

from pdf_redact.page_ranges import parse_page_range, pages_label


def test_all_and_empty():
    assert parse_page_range(None, 5) == [0, 1, 2, 3, 4]
    assert parse_page_range("all", 3) == [0, 1, 2]
    assert parse_page_range("", 2) == [0, 1]


def test_ranges_and_lists():
    assert parse_page_range("1-3", 10) == [0, 1, 2]
    assert parse_page_range("1,3,5-7", 10) == [0, 2, 4, 5, 6]
    assert parse_page_range("8-", 10) == [7, 8, 9]
    assert parse_page_range("-3", 10) == [0, 1, 2]


def test_out_of_range_single():
    with pytest.raises(ValueError):
        parse_page_range("99", 10)


def test_pages_label():
    assert "all" in pages_label(range(5), 5)
    assert pages_label([0, 1], 10).startswith("2 of")


def test_zero_pages():
    assert parse_page_range("all", 0) == []

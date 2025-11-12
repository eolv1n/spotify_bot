# tests/unit/test_basic.py
import pytest

def test_math_addition():
    """Пример самого простого юнит-теста."""
    assert 2 + 3 == 5


def test_string_contains():
    """Проверка строки."""
    s = "spotify bot"
    assert "bot" in s


@pytest.mark.parametrize("text, expected", [
    ("HELLO".lower(), "hello"),
    ("Bot".capitalize(), "Bot"),
])
def test_parametrized(text, expected):
    assert text == expected

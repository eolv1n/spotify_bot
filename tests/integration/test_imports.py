# tests/integration/test_imports.py
import importlib

def test_bot_imports():
    """Проверяем, что главный модуль проекта импортируется без ошибок."""
    module = importlib.import_module("bot")
    assert module is not None

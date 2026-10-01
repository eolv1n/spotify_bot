from unittest.mock import Mock, patch

from app import sources


def test_yandex_client_passes_explicit_proxy_without_global_session_changes(monkeypatch):
    monkeypatch.setattr(sources, "_yandex_client", None)
    monkeypatch.setattr(sources, "YANDEX_PROXY_URL", "http://192.0.2.1:21081")
    client = Mock()
    with patch.object(sources, "YandexRequest") as request, patch.object(sources, "YandexMusicClient") as factory:
        factory.return_value.init.return_value = client
        assert sources.get_yandex_client() is client
        assert sources.get_yandex_client() is client
        request.assert_called_once_with(proxy_url="http://192.0.2.1:21081", timeout=15)
        factory.assert_called_once_with(request=request.return_value)


def test_direct_local_yandex_client_keeps_bounded_timeout(monkeypatch):
    monkeypatch.setattr(sources, "_yandex_client", None)
    monkeypatch.setattr(sources, "YANDEX_PROXY_URL", None)
    with patch.object(sources, "YandexRequest") as request, patch.object(sources, "YandexMusicClient"):
        sources.get_yandex_client()
        request.assert_called_once_with(proxy_url=None, timeout=15)

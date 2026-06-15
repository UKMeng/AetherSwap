import json

import pytest


def test_buff_page_expired_is_verification_required():
    from buff.buyer import _is_verification_required

    assert _is_verification_required({"code": "FAIL", "msg": "页面已过期，请刷新当前页面"})


def test_make_request_raises_verification_required(monkeypatch):
    from buff.buyer import BuffBuyer, BuffVerificationRequired

    class FakeResponse:
        status_code = 200
        text = '{"code":"FAIL","msg":"页面已过期，请刷新当前页面"}'

        def json(self):
            return {"code": "FAIL", "msg": "页面已过期，请刷新当前页面"}

    monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse())
    buyer = BuffBuyer("csrf_token=abc")

    with pytest.raises(BuffVerificationRequired):
        buyer._make_request("POST", "https://buff.163.com/api/fake")


class _FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def test_buff_single_buy_payload_uses_receive_steam_id(monkeypatch):
    from buff.buyer import API_BUY, BuffBuyer

    receive_steam_id = "76561198000000002"
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url == API_BUY:
            return _FakeResponse({"code": "OK", "data": {"id": "bill-1"}})
        return _FakeResponse({"code": "OK", "data": {}})

    monkeypatch.setattr("requests.request", fake_request)
    buyer = BuffBuyer("csrf_token=abc", receive_steam_id=receive_steam_id)

    result = buyer.lock_and_get_pay_url("csgo", 123, "sell-1", "12.34")

    assert result["success"] is True
    payload = json.loads(next(kwargs["data"] for _, url, kwargs in calls if url == API_BUY))
    assert payload["steamid"] == receive_steam_id


def test_buff_batch_payloads_use_receive_steam_id(monkeypatch):
    from buff.buyer import API_BATCH_BUY_CREATE, API_BUY, BuffBuyer, PAY_METHOD_WECHAT

    receive_steam_id = "76561198000000002"
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url == API_BATCH_BUY_CREATE:
            return _FakeResponse({"code": "OK", "data": {"id": "batch-1"}})
        if url == API_BUY:
            return _FakeResponse({"code": "OK", "data": {"id": "bill-1"}})
        return _FakeResponse({"code": "OK", "data": {}})

    monkeypatch.setattr("requests.request", fake_request)
    buyer = BuffBuyer("csrf_token=abc", pay_method=PAY_METHOD_WECHAT, receive_steam_id=receive_steam_id)

    assert buyer.batch_buy_create(123, 12.34, 2) == "batch-1"
    assert buyer.batch_buy_finalize("csgo", 123, "sell-1", "12.34", "batch-1") == "bill-1"

    payloads = [json.loads(kwargs["data"]) for _, _, kwargs in calls if "data" in kwargs]
    assert payloads[0]["steamid"] == receive_steam_id
    assert payloads[1]["steamid"] == receive_steam_id


def test_buff_ask_seller_payload_uses_receive_steam_id(monkeypatch):
    from buff.buyer import API_ASK_SELLER_SEND, BuffBuyer

    receive_steam_id = "76561198000000002"
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _FakeResponse({"code": "OK", "data": {}})

    monkeypatch.setattr("requests.request", fake_request)
    buyer = BuffBuyer("csrf_token=abc", receive_steam_id=receive_steam_id)

    assert buyer.ask_seller_to_send(["bill-1"]) is True

    payload = json.loads(next(kwargs["data"] for _, url, kwargs in calls if url == API_ASK_SELLER_SEND))
    assert payload["steamid"] == receive_steam_id


def test_buff_client_factory_passes_receive_steam_id():
    from app.services.buff_client import create_buff_client_from_config

    receive_steam_id = "76561198000000002"
    client = create_buff_client_from_config(
        {"cookies": "csrf_token=abc"},
        {"buff": {"pay_method": "alipay"}},
        receive_steam_id=receive_steam_id,
    )

    assert client.receive_steam_id == receive_steam_id
    assert client._buyer.receive_steam_id == receive_steam_id


def test_resolve_steam_id_falls_back_to_steam_cookie():
    from config import resolve_steam_id

    assert resolve_steam_id({
        "cookies": "sessionid=abc; steamLoginSecure=76561198000000002%7C%7Ctoken"
    }) == "76561198000000002"

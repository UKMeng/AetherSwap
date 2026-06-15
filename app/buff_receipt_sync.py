import time
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from app.config_loader import (
    get_buff_credentials,
    get_steam_credentials,
    load_app_config_validated,
    resolve_steam_id_from_credentials,
)
from app.services.buff_client import create_buff_client_from_config
from app.state import get_inventory, get_purchases, update_purchase, update_purchase_by_id
from buff.buyer import API_HISTORY, BuffAuthExpired, BuffVerificationRequired

SUCCESS_STATES = {"SUCCESS"}
TERMINAL_FAILURE_STATES = {"FAIL", "CANCEL", "CANCELLED"}
DEFAULT_LOOKBACK_PAGES = 3
DEFAULT_PAGE_SIZE = 100
LEGACY_MATCH_WINDOW_SECONDS = 30 * 60
LEGACY_MATCH_CLOCK_SKEW_SECONDS = 120


def _clean(value) -> str:
    return str(value or "").strip()


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_key(value) -> Optional[int]:
    price = _to_float(value)
    if price is None:
        return None
    return int(round(price * 100))


def _order_id(order: dict) -> str:
    return _clean(order.get("id") or order.get("bill_order_id"))


def _order_state(order: dict) -> str:
    return _clean(order.get("state")).upper()


def _order_state_text(order: dict) -> str:
    return _clean(order.get("state_text") or order.get("status_text"))


def _is_success(order: dict) -> bool:
    return _order_state(order) in SUCCESS_STATES


def _is_relevant_order(order: dict) -> bool:
    state = _order_state(order)
    return bool(_order_id(order)) and state not in TERMINAL_FAILURE_STATES


def _assetid_sort_key(assetid: str) -> tuple:
    try:
        return 0, int(assetid)
    except (TypeError, ValueError):
        return 1, str(assetid)


def _order_time(order: dict) -> float:
    return _to_float(order.get("created_at") or order.get("created_time")) or 0.0


def _purchase_name(purchase: dict) -> str:
    return _clean(purchase.get("market_hash_name") or purchase.get("name"))


def fetch_buff_buy_history_orders(
    *,
    max_pages: int = DEFAULT_LOOKBACK_PAGES,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Tuple[bool, List[dict], str]:
    cred = get_buff_credentials() or {}
    if not cred.get("cookies"):
        return False, [], "未配置 Buff Cookie"

    cfg = load_app_config_validated()
    game = (cfg.get("buff") or {}).get("game", "csgo")
    client = create_buff_client_from_config(
        cred,
        cfg,
        receive_steam_id=resolve_steam_id_from_credentials(get_steam_credentials()),
    )
    orders: List[dict] = []
    try:
        for page_num in range(1, max(1, int(max_pages)) + 1):
            params = {
                "game": game,
                "page_num": str(page_num),
                "page_size": str(max(1, int(page_size))),
                "_": str(int(time.time() * 1000)),
            }
            data = client._buyer._make_request("GET", API_HISTORY, params=params)
            if data.get("code") != "OK":
                return False, orders, str(data.get("error") or data.get("msg") or data.get("code") or "Buff history 请求失败")
            batch = (data.get("data") or {}).get("items") or []
            orders.extend([o for o in batch if isinstance(o, dict) and _is_relevant_order(o)])
            total_page = int((data.get("data") or {}).get("total_page") or 0)
            if not batch or (total_page and page_num >= total_page):
                break
    except BuffAuthExpired:
        return False, orders, "Buff 登录已过期"
    except BuffVerificationRequired as e:
        return False, orders, str(e) or "Buff 需要验证"
    except Exception as e:
        return False, orders, str(e)[:200]
    return True, orders, ""


def _purchase_order_id(purchase: dict) -> str:
    return _clean(purchase.get("buff_order_id"))


def _legacy_group_key(record: dict) -> Optional[tuple]:
    goods_id = record.get("goods_id")
    price = _price_key(record.get("price"))
    if goods_id is None or price is None:
        return None
    try:
        goods_id = int(goods_id)
    except (TypeError, ValueError):
        return None
    if goods_id <= 0:
        return None
    return goods_id, price


def _within_legacy_window(purchase: dict, order: dict) -> bool:
    purchase_at = _to_float(purchase.get("at"))
    order_at = _to_float(order.get("created_at") or order.get("created_time"))
    if purchase_at is None or order_at is None:
        return False
    return -LEGACY_MATCH_CLOCK_SKEW_SECONDS <= purchase_at - order_at <= LEGACY_MATCH_WINDOW_SECONDS


def _legacy_matches(purchases: List[Tuple[int, dict]], orders: List[dict]) -> Dict[int, dict]:
    purchases_by_key = defaultdict(list)
    orders_by_key = defaultdict(list)
    for idx, purchase in purchases:
        if _purchase_order_id(purchase):
            continue
        key = _legacy_group_key(purchase)
        if key is not None:
            purchases_by_key[key].append((idx, purchase))
    for order in orders:
        key = _legacy_group_key(order)
        if key is not None:
            orders_by_key[key].append(order)

    matches: Dict[int, dict] = {}
    for key, grouped_purchases in purchases_by_key.items():
        grouped_orders = [
            order
            for order in orders_by_key.get(key, [])
            if any(_within_legacy_window(purchase, order) for _, purchase in grouped_purchases)
        ]
        if len(grouped_orders) != len(grouped_purchases):
            continue
        grouped_purchases.sort(key=lambda x: (x[1].get("at") or 0, x[1].get("_db_id") or 0, x[0]))
        grouped_orders.sort(key=lambda x: (x.get("created_at") or x.get("created_time") or 0, _order_id(x)))
        for (idx, _purchase), order in zip(grouped_purchases, grouped_orders):
            matches[idx] = order
    return matches


def _update_payload(order: dict) -> dict:
    payload = {
        "buff_order_id": _order_id(order),
        "buff_state": _order_state(order),
    }
    state_text = _order_state_text(order)
    if state_text:
        payload["buff_state_text"] = state_text
    payload["pending_receipt"] = not _is_success(order)
    if not _is_success(order):
        payload["assetid"] = None
    return payload


def _inventory_candidates_by_name(inv_items: Iterable[dict], used_assetids: set) -> Dict[str, List[str]]:
    candidates = defaultdict(list)
    for item in inv_items or []:
        aid = _clean(item.get("assetid"))
        if not aid or aid in used_assetids:
            continue
        for name in {
            _clean(item.get("market_hash_name")),
            _clean(item.get("name")),
        }:
            if name:
                candidates[name].append(aid)
    for name in candidates:
        candidates[name] = sorted(set(candidates[name]), key=_assetid_sort_key)
    return dict(candidates)


def _load_inventory_items() -> List[dict]:
    inv_items = get_inventory() or []
    if inv_items:
        return inv_items
    try:
        from app.inventory_cs2 import scan_cs2_inventory

        ok, scanned, _ = scan_cs2_inventory()
        if ok:
            return scanned or []
    except Exception:
        pass
    return []


def _assetid_assignments(
    purchases: List[Tuple[int, dict]],
    matched_orders: Dict[int, dict],
    inv_items: Iterable[dict],
) -> Dict[int, str]:
    successful = [
        (idx, purchase, matched_orders[idx])
        for idx, purchase in purchases
        if idx in matched_orders
        if _is_success(matched_orders[idx])
    ]
    if not successful:
        return {}

    success_indices = {idx for idx, _, _ in successful}
    used_by_other = {
        _clean(purchase.get("assetid"))
        for idx, purchase in purchases
        if idx not in success_indices and _clean(purchase.get("assetid"))
    }
    candidates_by_name = _inventory_candidates_by_name(inv_items, used_by_other)
    groups = defaultdict(list)
    for idx, purchase, order in successful:
        name = _purchase_name(purchase)
        if name:
            groups[name].append((idx, purchase, order))

    assignments: Dict[int, str] = {}
    for name, group in groups.items():
        candidates = candidates_by_name.get(name) or []
        if len(candidates) != len(group):
            continue
        group.sort(key=lambda x: (_order_time(x[2]), x[1].get("at") or 0, x[1].get("_db_id") or 0, x[0]))
        for (idx, _purchase, _order), aid in zip(group, candidates):
            assignments[idx] = aid
    return assignments


def sync_pending_receipts_from_buff_history(
    *,
    get_purchases_fn: Callable[[], List[dict]] = get_purchases,
    update_purchase_fn: Callable[[int, Dict], bool] = update_purchase,
    update_purchase_by_id_fn: Callable[[int, Dict], bool] = update_purchase_by_id,
    orders: Optional[Iterable[dict]] = None,
    inventory_items: Optional[Iterable[dict]] = None,
    attach_assetids: bool = True,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> Tuple[bool, Dict[str, object]]:
    if orders is None:
        ok, fetched_orders, err = fetch_buff_buy_history_orders()
        if not ok:
            return False, {"error": err}
        orders = fetched_orders

    orders = list(orders or [])
    order_by_id = {_order_id(order): order for order in orders if _order_id(order)}
    purchases = list(enumerate(get_purchases_fn() or []))
    legacy = _legacy_matches(purchases, orders)
    matched_orders: Dict[int, dict] = {}

    for idx, purchase in purchases:
        order_id = _purchase_order_id(purchase)
        if order_id and order_id in order_by_id:
            matched_orders[idx] = order_by_id[order_id]
        elif idx in legacy:
            matched_orders[idx] = legacy[idx]

    assetid_assignments: Dict[int, str] = {}
    if attach_assetids:
        inv_items = list(inventory_items) if inventory_items is not None else _load_inventory_items()
        assetid_assignments = _assetid_assignments(purchases, matched_orders, inv_items)

    updated = 0
    assetid_updated = 0
    exact = 0
    legacy_count = 0
    for idx, purchase in purchases:
        order = matched_orders.get(idx)
        order_id = _purchase_order_id(purchase)
        if not order:
            continue
        if order_id:
            exact += 1
        else:
            legacy_count += 1

        payload = _update_payload(order)
        if idx in assetid_assignments:
            payload["assetid"] = assetid_assignments[idx]
        current = {
            "buff_order_id": _purchase_order_id(purchase) or None,
            "buff_state": _clean(purchase.get("buff_state")) or None,
            "buff_state_text": _clean(purchase.get("buff_state_text")) or None,
            "pending_receipt": bool(purchase.get("pending_receipt")),
            "assetid": _clean(purchase.get("assetid")) or None,
        }
        desired = {
            "buff_order_id": payload.get("buff_order_id"),
            "buff_state": payload.get("buff_state"),
            "buff_state_text": payload.get("buff_state_text"),
            "pending_receipt": payload.get("pending_receipt"),
            "assetid": payload.get("assetid", current.get("assetid")),
        }
        assetid_changed = "assetid" in payload and current.get("assetid") != payload.get("assetid")
        if all(current.get(k) == desired.get(k) for k in desired):
            continue

        db_id = purchase.get("_db_id")
        ok_update = update_purchase_by_id_fn(db_id, payload) if db_id else update_purchase_fn(idx, payload)
        if ok_update:
            updated += 1
            if assetid_changed:
                assetid_updated += 1

    if updated and log_fn:
        log_fn(
            f"Buff 订单同步：更新 {updated} 条收货状态（精确 {exact}，历史匹配 {legacy_count}，assetid {assetid_updated}）",
            "info",
        )
    return True, {"updated": updated, "exact": exact, "legacy": legacy_count, "assetids": assetid_updated}

from app.buff_receipt_sync import sync_pending_receipts_from_buff_history


def test_sync_pending_receipts_uses_exact_buff_order_id():
    purchases = [
        {
            "_db_id": 1,
            "name": "Desert Eagle | Blue Ply (Field-Tested)",
            "goods_id": 779217,
            "price": 2.0,
            "at": 100,
            "pending_receipt": True,
            "buff_order_id": "order-1",
        }
    ]
    orders = [
        {
            "id": "order-1",
            "goods_id": 779217,
            "price": "2",
            "created_at": 90,
            "state": "SUCCESS",
            "state_text": "购买成功",
        }
    ]
    updates = {}

    ok, result = sync_pending_receipts_from_buff_history(
        get_purchases_fn=lambda: purchases,
        update_purchase_fn=lambda idx, data: False,
        update_purchase_by_id_fn=lambda db_id, data: updates.setdefault(db_id, data) or True,
        orders=orders,
        inventory_items=[{"market_hash_name": "Desert Eagle | Blue Ply (Field-Tested)", "assetid": "asset-1"}],
    )

    assert ok is True
    assert result["updated"] == 1
    assert result["assetids"] == 1
    assert updates[1]["pending_receipt"] is False
    assert updates[1]["assetid"] == "asset-1"
    assert updates[1]["buff_state"] == "SUCCESS"


def test_sync_pending_receipts_matches_legacy_rows_by_buff_order_sequence():
    purchases = [
        {
            "_db_id": 1,
            "name": "Desert Eagle | Blue Ply (Field-Tested)",
            "goods_id": 779217,
            "price": 2.19,
            "at": 1781540559.447,
            "pending_receipt": True,
        },
        {
            "_db_id": 2,
            "name": "Desert Eagle | Blue Ply (Field-Tested)",
            "goods_id": 779217,
            "price": 2.19,
            "at": 1781540559.454,
            "pending_receipt": True,
        },
    ]
    orders = [
        {
            "id": "success-order",
            "goods_id": 779217,
            "price": "2.19",
            "created_at": 1781540559,
            "state": "SUCCESS",
            "state_text": "购买成功",
        },
        {
            "id": "pending-order",
            "goods_id": 779217,
            "price": "2.19",
            "created_at": 1781540558,
            "state": "TO_DELIVER",
            "state_text": "等待卖家发起报价",
        },
    ]
    updates = {}

    ok, result = sync_pending_receipts_from_buff_history(
        get_purchases_fn=lambda: purchases,
        update_purchase_fn=lambda idx, data: False,
        update_purchase_by_id_fn=lambda db_id, data: updates.setdefault(db_id, data) or True,
        orders=orders,
        inventory_items=[{"market_hash_name": "Desert Eagle | Blue Ply (Field-Tested)", "assetid": "asset-2"}],
    )

    assert ok is True
    assert result["updated"] == 2
    assert updates[1]["buff_order_id"] == "pending-order"
    assert updates[1]["pending_receipt"] is True
    assert updates[1]["assetid"] is None
    assert updates[2]["buff_order_id"] == "success-order"
    assert updates[2]["pending_receipt"] is False
    assert updates[2]["assetid"] == "asset-2"


def test_sync_pending_receipts_does_not_guess_assetid_when_inventory_is_ambiguous():
    purchases = [
        {
            "_db_id": 1,
            "name": "Desert Eagle | Blue Ply (Field-Tested)",
            "goods_id": 779217,
            "price": 2.16,
            "at": 100,
            "pending_receipt": True,
            "buff_order_id": "order-1",
        }
    ]
    orders = [
        {
            "id": "order-1",
            "goods_id": 779217,
            "price": "2.16",
            "created_at": 90,
            "state": "SUCCESS",
            "state_text": "购买成功",
        }
    ]
    updates = {}

    ok, result = sync_pending_receipts_from_buff_history(
        get_purchases_fn=lambda: purchases,
        update_purchase_fn=lambda idx, data: False,
        update_purchase_by_id_fn=lambda db_id, data: updates.setdefault(db_id, data) or True,
        orders=orders,
        inventory_items=[
            {"market_hash_name": "Desert Eagle | Blue Ply (Field-Tested)", "assetid": "asset-1"},
            {"market_hash_name": "Desert Eagle | Blue Ply (Field-Tested)", "assetid": "asset-2"},
        ],
    )

    assert ok is True
    assert result["updated"] == 1
    assert result["assetids"] == 0
    assert updates[1]["pending_receipt"] is False
    assert "assetid" not in updates[1]


def test_sync_pending_receipts_does_not_count_unchanged_assetid():
    purchases = [
        {
            "_db_id": 1,
            "name": "Desert Eagle | Blue Ply (Field-Tested)",
            "goods_id": 779217,
            "price": 2.0,
            "at": 100,
            "pending_receipt": False,
            "buff_order_id": "order-1",
            "buff_state": "SUCCESS",
            "buff_state_text": "购买成功",
            "assetid": "asset-1",
        }
    ]
    orders = [
        {
            "id": "order-1",
            "goods_id": 779217,
            "price": "2",
            "created_at": 90,
            "state": "SUCCESS",
            "state_text": "购买成功",
        }
    ]
    updates = {}

    ok, result = sync_pending_receipts_from_buff_history(
        get_purchases_fn=lambda: purchases,
        update_purchase_fn=lambda idx, data: False,
        update_purchase_by_id_fn=lambda db_id, data: updates.setdefault(db_id, data) or True,
        orders=orders,
        inventory_items=[{"market_hash_name": "Desert Eagle | Blue Ply (Field-Tested)", "assetid": "asset-1"}],
    )

    assert ok is True
    assert result["updated"] == 0
    assert result["assetids"] == 0
    assert updates == {}

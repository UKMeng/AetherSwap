"""Status, log, plan, and payment-related routes."""
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter
from app.state import (
    clear_log,
    confirm_payment,
    get_log,
    get_pending_payment,
    get_plan,
    get_status,
    set_pending_payment,
)
from config import get_buff, get_steam, resolve_steam_id
from app.accounts import get_current_id, list_accounts
from pydantic import BaseModel
router = APIRouter()
class ConfirmBody(BaseModel):
    ok: bool
def _steam_receive_account_snapshot() -> dict:
    steam_creds = get_steam()
    cookies = (steam_creds.get("cookies") or "").strip()
    steam_id = resolve_steam_id(steam_creds)
    accounts = list_accounts()
    current_id = get_current_id()
    matched = next((a for a in accounts if (a.get("steam_id") or "").strip() == steam_id), None)
    return {
        "steam_id": steam_id,
        "has_cookie": bool(cookies),
        "account_id": matched.get("id") if matched else "",
        "username": matched.get("username") if matched else "",
        "display_name": matched.get("display_name") if matched else "",
        "current_account_id": current_id or "",
        "is_current_account": bool(matched and current_id and matched.get("id") == current_id),
    }
@router.get("/api/status")
def api_status():
    st = get_status()
    buff_creds = get_buff()
    st["buff_no_cookie"] = not bool((buff_creds.get("cookies") or "").strip())
    st["steam_receive_account"] = _steam_receive_account_snapshot()
    return st

@router.get("/api/log")
def api_log(since: int = 0):
    return {"lines": get_log(since)}
@router.post("/api/log/clear")
def api_log_clear():
    clear_log()
    return {"ok": True}
@router.post("/api/log/export")
def api_log_export():
    lines = get_log(0)
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = log_dir / f"debug_{ts}.txt"
    def fmt_time(t):
        if t is None:
            return ""
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    content = "\n".join(
        f"{fmt_time(e.get('t'))} [{e.get('level', 'info')}] {e.get('msg', '')}"
        for e in lines
    ) + "\n"
    filename.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(filename), "lines": len(lines)}
@router.get("/api/plan")
def api_plan():
    return {"plan": get_plan()}
@router.get("/api/pending_payment")
def api_pending_payment():
    return {"pending": get_pending_payment()}
@router.post("/api/confirm_payment")
def api_confirm_payment(body: ConfirmBody):
    confirm_payment(body.ok)
    set_pending_payment(None)
    return {"ok": True}

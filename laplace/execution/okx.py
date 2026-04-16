"""
laplace/execution/okx.py
OKX 交易执行接口 —— 下单 / 撤单 / 查询仓位。

在 RUN_MODE=paper 时所有下单操作只打印日志，不真实发送请求。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.config import config
from laplace.utils.okx_client import OKXClient


class OKXExecutor:
    """OKX 交易执行器。

    功能：
        - open_long / open_short：市价开仓
        - close_position：市价平仓
        - get_position：查询当前仓位
        - get_balance：查询账户余额

    paper 模式下所有写操作仅记录日志，不发送真实请求。
    """

    def __init__(
        self,
        inst_id: str = "BTC-USDT-SWAP",
        lever:   str = "5",
        client:  OKXClient | None = None,
    ) -> None:
        self.inst_id = inst_id
        self.lever   = lever
        self.client  = client or OKXClient()
        self.paper   = config.RUN_MODE != "live"

        # 交易记录存储（paper 模式）
        self._trade_log: Path = config.SIGNALS_DIR / "trades.json"

    # ── 开仓 ─────────────────────────────────────────────────────

    def open_long(self, size: str, price: float | None = None) -> dict:
        """市价开多。"""
        return self._place_order(side="buy", pos_side="long", size=size, price=price)

    def open_short(self, size: str, price: float | None = None) -> dict:
        """市价开空。"""
        return self._place_order(side="sell", pos_side="short", size=size, price=price)

    # ── 平仓 ─────────────────────────────────────────────────────

    def close_position(self, pos_side: str = "long") -> dict:
        """市价平仓。

        Args:
            pos_side: "long" 或 "short"
        """
        body = {
            "instId":  self.inst_id,
            "mgnMode": "cross",
            "posSide": pos_side,
        }
        return self._exec_or_paper("POST", "/api/v5/trade/close-position", body)

    # ── 查询 ─────────────────────────────────────────────────────

    def get_position(self) -> list[dict]:
        """查询当前合约仓位。"""
        resp = self.client.get_priv(
            f"/api/v5/account/positions?instId={self.inst_id}"
        )
        return resp.get("data", [])

    def get_balance(self, ccy: str = "USDT") -> float:
        """查询指定币种可用余额。"""
        resp = self.client.get_priv("/api/v5/account/balance")
        for item in resp.get("data", [{}])[0].get("details", []):
            if item.get("ccy") == ccy:
                return float(item.get("availBal", 0))
        return 0.0

    # ── 内部工具 ──────────────────────────────────────────────────

    def _place_order(
        self,
        side:     str,
        pos_side: str,
        size:     str,
        price:    float | None = None,
    ) -> dict:
        """构造下单请求。"""
        ord_type = "market" if price is None else "limit"
        body: dict[str, Any] = {
            "instId":  self.inst_id,
            "tdMode":  "cross",
            "side":    side,
            "posSide": pos_side,
            "ordType": ord_type,
            "sz":      size,
            "lever":   self.lever,
        }
        if price is not None:
            body["px"] = str(price)
        return self._exec_or_paper("POST", "/api/v5/trade/order", body)

    def _exec_or_paper(self, method: str, path: str, body: dict) -> dict:
        """在 live 模式执行真实请求；paper 模式只记录日志。"""
        ts = datetime.now(timezone.utc).isoformat()
        if self.paper:
            record = {"ts": ts, "mode": "paper", "method": method, "path": path, "body": body}
            self._append_trade(record)
            print(f"  [PAPER] {method} {path} | {json.dumps(body)}")
            return {"code": "0", "msg": "paper_mode", "data": []}
        else:
            resp = self.client.post_priv(path, body)
            record = {"ts": ts, "mode": "live", "path": path, "body": body, "resp": resp}
            self._append_trade(record)
            return resp

    def _append_trade(self, record: dict) -> None:
        """追加交易记录到 signals/trades.json。"""
        self._trade_log.parent.mkdir(parents=True, exist_ok=True)
        trades = []
        if self._trade_log.exists():
            try:
                trades = json.loads(self._trade_log.read_text())
            except Exception:
                pass
        trades.append(record)
        self._trade_log.write_text(json.dumps(trades, indent=2, ensure_ascii=False))

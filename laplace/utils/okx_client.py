"""
laplace/utils/okx_client.py
OKX REST API 客户端 —— 签名封装与请求工具。

提取自 ~/ctis-agent/engine.py，适配 LaplaceSignal 模块化架构。

公开接口：
    okx_pub(path)             ── 无需签名的公开接口
    okx_priv(path, method)    ── 需要 HMAC-SHA256 签名的私有接口
    OKXClient                 ── 面向对象封装（推荐使用）
"""

import base64
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import requests

from laplace.config import config


# ================================================================
# 函数式 API（与旧 engine.py 兼容）
# ================================================================

def okx_pub(path: str, params: dict | None = None, timeout: int = 8) -> dict:
    """调用 OKX 公开（无需鉴权）接口。

    Args:
        path:    API 路径，例如 "/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H"
        params:  URL 查询参数（与 path 中的参数合并，可选）
        timeout: 请求超时秒数

    Returns:
        JSON 响应字典；出错时返回空字典 {}。
    """
    try:
        url = config.OKX_BASE_URL + path
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # 静默失败：调用方通过返回空字典判断
        _log_error("okx_pub", path, e)
        return {}


def okx_priv(
    path: str,
    method: str = "GET",
    body: dict | None = None,
    timeout: int = 8,
) -> dict:
    """调用 OKX 私有（需鉴权）接口。

    使用 HMAC-SHA256 + Base64 签名，符合 OKX API v5 规范。

    Args:
        path:    API 路径（含查询字符串），例如 "/api/v5/account/balance"
        method:  HTTP 方法，"GET" 或 "POST"
        body:    POST 请求体字典（GET 时传 None）
        timeout: 请求超时秒数

    Returns:
        JSON 响应字典；出错时返回空字典 {}。
    """
    try:
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        body_str = ""
        if body:
            import json
            body_str = json.dumps(body)
        msg = ts + method.upper() + path + body_str
        sig = base64.b64encode(
            hmac.new(
                config.OKX_API_SECRET.encode(),
                msg.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        headers = {
            "OK-ACCESS-KEY":        config.OKX_API_KEY,
            "OK-ACCESS-SIGN":       sig,
            "OK-ACCESS-TIMESTAMP":  ts,
            "OK-ACCESS-PASSPHRASE": config.OKX_API_PASSPHRASE,
            "Content-Type":         "application/json",
        }
        url = config.OKX_BASE_URL + path
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, headers=headers, data=body_str, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _log_error("okx_priv", path, e)
        return {}


# ================================================================
# 面向对象封装（推荐）
# ================================================================

class OKXClient:
    """OKX REST API 客户端。

    自动注入 config 中的 API Key / Secret / Passphrase，
    提供 get_pub / get_priv / post_priv 三个方法。

    用法：
        client = OKXClient()
        data   = client.get_pub("/api/v5/market/tickers?instType=SWAP")
        acct   = client.get_priv("/api/v5/account/balance")
    """

    def __init__(
        self,
        api_key:    str = "",
        api_secret: str = "",
        passphrase: str = "",
        base_url:   str = "",
    ) -> None:
        self.api_key    = api_key    or config.OKX_API_KEY
        self.api_secret = api_secret or config.OKX_API_SECRET
        self.passphrase = passphrase or config.OKX_API_PASSPHRASE
        self.base_url   = base_url   or config.OKX_BASE_URL

    # ── 公开接口 ──────────────────────────────────────────────────

    def get_pub(self, path: str, params: dict | None = None, timeout: int = 8) -> dict:
        """GET 公开接口。"""
        try:
            r = requests.get(self.base_url + path, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _log_error("OKXClient.get_pub", path, e)
            return {}

    # ── 私有接口 ──────────────────────────────────────────────────

    def _sign_headers(self, method: str, path: str, body_str: str = "") -> dict:
        """生成 OKX v5 鉴权头。"""
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        msg = ts + method.upper() + path + body_str
        sig = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                msg.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY":        self.api_key,
            "OK-ACCESS-SIGN":       sig,
            "OK-ACCESS-TIMESTAMP":  ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type":         "application/json",
        }

    def get_priv(self, path: str, timeout: int = 8) -> dict:
        """GET 私有接口（带签名）。"""
        try:
            headers = self._sign_headers("GET", path)
            r = requests.get(self.base_url + path, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _log_error("OKXClient.get_priv", path, e)
            return {}

    def post_priv(self, path: str, body: dict, timeout: int = 8) -> dict:
        """POST 私有接口（带签名）。"""
        import json as _json
        try:
            body_str = _json.dumps(body)
            headers  = self._sign_headers("POST", path, body_str)
            r = requests.post(self.base_url + path, headers=headers, data=body_str, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _log_error("OKXClient.post_priv", path, e)
            return {}

    def __repr__(self) -> str:
        key_preview = self.api_key[:6] + "..." if self.api_key else "(unset)"
        return f"OKXClient(key={key_preview}, base={self.base_url})"


# ================================================================
# 内部工具
# ================================================================

def _log_error(caller: str, path: str, err: Exception) -> None:
    """统一错误日志（后续可替换为 logging 模块）。"""
    print(f"  [OKXClient] {caller} {path} ERROR: {err}")

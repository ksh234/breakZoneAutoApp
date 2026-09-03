"""키움 REST/WebSocket 브로커 구현체 (동기 REST + 스레드 WebSocket, D-011).

스펙 출처(2026-09-02 실측): docs/01-broker-kiwoom.md "확정 스펙" 표.
- REST: 토큰(/oauth2/token), 주문(kt10000/1/3), 현재가(ka10001), 잔고(kt00018), 미체결(ka10075).
- WebSocket: /api/dostk/websocket, LOGIN→REG(0B 체결)→REAL, PING echo.

전략 코드는 이 클래스를 직접 부르지 않고 BrokerAdapter 인터페이스만 사용한다.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import requests

from .base import BrokerAdapter
from .errors import AuthError, BrokerError, OrderRejected, RateLimited, TransientError
from .models import Balance, Order, OrderStatus, OrderType, Position, Side

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
JSON_CT = "application/json;charset=UTF-8"


# ─── 순수 유틸 (테스트 가능) ──────────────────────────
def to_int(v: Any, *, signed: bool = False) -> int:
    """키움 숫자 문자열('+57800', '-1,200', '00123')을 int 로. 실패 시 0."""
    if v is None:
        return 0
    s = str(v).strip()
    if not s:
        return 0
    neg = s.lstrip().startswith("-")
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return 0
    n = int(digits)
    return -n if (signed and neg) else n


def clean_code(v: Any) -> str:
    """종목코드 정규화('A005930'→'005930'). 6자리 zero-pad."""
    if not v:
        return ""
    d = re.sub(r"[^\d]", "", str(v))
    return d[-6:].zfill(6) if d else ""


def first_list(data: dict) -> list:
    """응답 dict 에서 첫 번째 list 값 반환(배열 래퍼 필드명이 불확실할 때)."""
    for v in data.values():
        if isinstance(v, list):
            return v
    return []


class _TokenBucket:
    """스레드안전 토큰버킷 레이트리미터."""

    def __init__(self, rate_per_sec: float, capacity: Optional[float] = None):
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity or rate_per_sec)
        self._tokens = self.capacity
        self._ts = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._ts) * self.rate)
                self._ts = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self.rate
            time.sleep(min(wait, 1.0))


class KiwoomRestBroker(BrokerAdapter):
    DEMO_REST = "https://mockapi.kiwoom.com"
    REAL_REST = "https://api.kiwoom.com"
    DEMO_WS = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
    REAL_WS = "wss://api.kiwoom.com:10000/api/dostk/websocket"

    def __init__(
        self, app_key: str, secret: str, account_no: str = "",
        mode: str = "demo", *, rate_per_sec: float = 5.0,
    ):
        if mode not in ("demo", "real"):
            raise ValueError(f"mode must be demo/real, got {mode!r}")
        self.mode = mode
        self.app_key = app_key
        self.secret = secret
        self.account_no = account_no
        self.base_rest = self.REAL_REST if mode == "real" else self.DEMO_REST
        self.ws_url = self.REAL_WS if mode == "real" else self.DEMO_WS

        self._token: Optional[str] = None
        self._token_exp: Optional[datetime] = None
        self._session = requests.Session()
        self._limiter = _TokenBucket(rate_per_sec)

        self._prices: dict[str, int] = {}
        self._lock = threading.Lock()
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_stop = threading.Event()
        self._ws_codes: list[str] = []
        self._on_tick: Optional[Callable[[str, int], None]] = None

    # ── 토큰 ──────────────────────────────────────────
    def connect(self) -> None:
        self._ensure_token()

    def _ensure_token(self) -> None:
        if self._token and self._token_exp and datetime.now(KST) < self._token_exp - timedelta(seconds=60):
            return
        self._issue_token()

    def _issue_token(self) -> None:
        try:
            r = self._session.post(
                self.base_rest + "/oauth2/token",
                headers={"Content-Type": JSON_CT},
                json={"grant_type": "client_credentials", "appkey": self.app_key, "secretkey": self.secret},
                timeout=10,
            )
        except requests.RequestException as e:
            raise AuthError(f"토큰 요청 네트워크 오류: {e}") from e
        try:
            data = r.json()
        except ValueError:
            raise AuthError(f"토큰 응답 JSON 아님: {r.text[:200]}")
        token = data.get("token") or data.get("access_token")
        if r.status_code != 200 or not token:
            raise AuthError(f"토큰 발급 실패 rc={data.get('return_code')} {data.get('return_msg')}")
        self._token = token
        self._token_exp = self._parse_expiry(data.get("expires_dt"))
        logger.info("키움 토큰 발급 완료 (만료 %s)", self._token_exp)

    @staticmethod
    def _parse_expiry(expires_dt: Any) -> datetime:
        s = str(expires_dt or "").strip()
        if len(s) == 14 and s.isdigit():  # yyyyMMddHHmmss
            try:
                return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=KST)
            except ValueError:
                pass
        return datetime.now(KST) + timedelta(hours=1)  # 안전 폴백

    # ── 요청 공통 ─────────────────────────────────────
    def _post(self, path: str, api_id: str, body: dict, *, retries: int = 3) -> tuple[dict, Any]:
        self._ensure_token()
        url = self.base_rest + path
        last: Optional[Exception] = None
        for attempt in range(retries):
            self._limiter.acquire()
            headers = {
                "authorization": f"Bearer {self._token}",
                "api-id": api_id,
                "Content-Type": JSON_CT,
            }
            try:
                r = self._session.post(url, headers=headers, json=body, timeout=10)
            except requests.RequestException as e:
                last = TransientError(f"{api_id} 네트워크 오류: {e}")
                self._backoff(attempt)
                continue
            if r.status_code == 429:
                last = RateLimited(f"{api_id} 429 rate limited")
                self._backoff(attempt)
                continue
            if r.status_code == 401:
                self._token = None
                self._ensure_token()
                last = AuthError(f"{api_id} 401")
                continue
            if r.status_code >= 500:
                last = TransientError(f"{api_id} {r.status_code}")
                self._backoff(attempt)
                continue
            try:
                data = r.json()
            except ValueError:
                raise BrokerError(f"{api_id} 응답 JSON 아님: {r.text[:200]}")
            rc = data.get("return_code")
            if rc not in (0, "0", None):
                raise BrokerError(f"{api_id} 실패 rc={rc}: {data.get('return_msg')}")
            return data, r.headers
        raise last or BrokerError(f"{api_id} 요청 실패")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(0.5 * (2 ** attempt), 4.0))

    # ── 시세 ──────────────────────────────────────────
    def get_price(self, code: str) -> Optional[int]:
        code = clean_code(code)
        with self._lock:
            cached = self._prices.get(code)
        if cached:
            return cached
        try:
            data, _ = self._post("/api/dostk/stkinfo", "ka10001", {"stk_cd": code})
        except BrokerError as e:
            logger.warning("현재가 조회 실패 %s: %s", code, e)
            return None
        price = to_int(data.get("cur_prc"))
        return price or None

    def get_prices(self, codes: list[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in codes:
            p = self.get_price(c)
            if p:
                out[clean_code(c)] = p
        return out

    def cached_price(self, code: str) -> Optional[int]:
        with self._lock:
            return self._prices.get(clean_code(code))

    # ── 주문 ──────────────────────────────────────────
    def place_order(
        self, code: str, side: Side, qty: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[int] = None, *, name: str = "", reason: str = "",
    ) -> Order:
        code = clean_code(code)
        if qty <= 0:
            raise OrderRejected(f"수량은 양의 정수여야 함: {qty}")
        if order_type == OrderType.LIMIT and not price:
            raise OrderRejected("지정가 주문은 price 필요")
        trde_tp = "3" if order_type == OrderType.MARKET else "0"
        ord_uv = "" if order_type == OrderType.MARKET else str(int(price))
        api_id = "kt10000" if side == Side.BUY else "kt10001"
        body = {
            "dmst_stex_tp": "KRX", "stk_cd": code, "ord_qty": str(int(qty)),
            "trde_tp": trde_tp, "ord_uv": ord_uv, "cond_uv": "",
        }
        data, _ = self._post("/api/dostk/ordr", api_id, body)
        ord_no = data.get("ord_no")
        if not ord_no:
            raise OrderRejected(f"주문번호 미수신 rc={data.get('return_code')} {data.get('return_msg')}")
        logger.info("주문 접수 %s %s %sx%s → ord_no=%s", code, side.value, order_type.value, qty, ord_no)
        return Order(
            code=code, name=name, side=side, qty=int(qty), order_type=order_type,
            price=price, status=OrderStatus.SUBMITTED, broker_order_id=str(ord_no),
            reason=reason, created_at=datetime.now(KST),
        )

    def cancel(self, order: Order, qty: Optional[int] = None) -> None:
        if not order.broker_order_id:
            raise BrokerError("취소할 주문번호(broker_order_id) 없음")
        cncl_qty = "0" if qty is None else str(int(qty))
        body = {
            "dmst_stex_tp": "KRX", "orig_ord_no": str(order.broker_order_id),
            "stk_cd": clean_code(order.code), "cncl_qty": cncl_qty,
        }
        self._post("/api/dostk/ordr", "kt10003", body)
        logger.info("주문 취소 요청 ord_no=%s qty=%s", order.broker_order_id, cncl_qty)

    def get_unfilled_orders(self) -> list[dict]:
        body = {"all_stk_tp": "0", "trde_tp": "0", "stex_tp": "KRX", "stk_cd": ""}
        data, _ = self._post("/api/dostk/acnt", "ka10075", body)
        rows = first_list(data)
        return [
            {"ord_no": str(r.get("ord_no", "")), "code": clean_code(r.get("stk_cd")),
             "unfilled_qty": to_int(r.get("oso_qty"))}
            for r in rows if isinstance(r, dict)
        ]

    # ── 계좌 ──────────────────────────────────────────
    def get_positions(self) -> list[Position]:
        data, _ = self._post("/api/dostk/acnt", "kt00018", {"qry_tp": "2", "dmst_stex_tp": "KRX"})
        out: list[Position] = []
        for r in data.get("acnt_evlt_remn_indv_tot") or first_list(data):
            if not isinstance(r, dict):
                continue
            qty = to_int(r.get("rmnd_qty"))
            if qty <= 0:
                continue
            out.append(Position(
                code=clean_code(r.get("stk_cd")), name=str(r.get("stk_nm", "") or ""),
                qty=qty, avg_price=to_int(r.get("pur_pric")),
                current_price=to_int(r.get("cur_prc")),
            ))
        return out

    def get_balance(self) -> Balance:
        data, _ = self._post("/api/dostk/acnt", "kt00018", {"qry_tp": "1", "dmst_stex_tp": "KRX"})
        equity = to_int(data.get("prsm_dpst_aset_amt"))       # 추정예탁자산(총자산)
        stock_value = to_int(data.get("tot_evlt_amt"))         # 총평가금액(주식)
        cash = max(0, equity - stock_value)                    # 주문가능현금 근사(실측 후 정밀화)
        return Balance(cash=cash, equity=equity or stock_value, stock_value=stock_value,
                       updated_at=datetime.now(KST))

    # ── 실시간 시세 (WebSocket, 스레드) ───────────────
    def subscribe_realtime(self, codes: list[str], on_tick: Callable[[str, int], None]) -> None:
        self._ws_codes = [clean_code(c) for c in codes if clean_code(c)]
        self._on_tick = on_tick
        if self._ws_thread and self._ws_thread.is_alive():
            self._send_reg()
            return
        self._ws_stop.clear()
        self._ws_thread = threading.Thread(target=self._ws_loop, name="kiwoom-ws", daemon=True)
        self._ws_thread.start()

    def _send_reg(self) -> None:
        if self._ws and self._ws_codes:
            self._ws.send(json.dumps({
                "trnm": "REG", "grp_no": "1", "refresh": "1",
                "data": [{"item": self._ws_codes, "type": ["0B"]}],
            }))

    def _ws_loop(self) -> None:
        try:
            import websocket  # websocket-client (지연 import)
        except ImportError:
            logger.error("websocket-client 미설치 — 실시간 시세 비활성. `pip install websocket-client`")
            return
        backoff = 1
        while not self._ws_stop.is_set():
            try:
                self._ensure_token()
                self._ws = websocket.create_connection(self.ws_url, timeout=30)
                self._ws.send(json.dumps({"trnm": "LOGIN", "token": self._token}))
                while not self._ws_stop.is_set():
                    try:
                        raw = self._ws.recv()
                    except Exception:
                        if self._ws_stop.is_set():
                            break
                        raise
                    if not raw:
                        continue
                    msg = json.loads(raw)
                    trnm = msg.get("trnm")
                    if trnm == "LOGIN":
                        if msg.get("return_code", 0) != 0:
                            raise AuthError(f"WS 로그인 실패: {msg.get('return_msg')}")
                        logger.info("WS 로그인 성공 → 실시간 등록 %s", self._ws_codes)
                        self._send_reg()
                    elif trnm == "PING":
                        self._ws.send(raw)  # 받은 프레임 그대로 echo
                    elif trnm == "REAL":
                        self._handle_real(msg.get("data", []))
                try:
                    self._ws.close()
                except Exception:
                    pass
                backoff = 1
            except Exception as e:
                if self._ws_stop.is_set():
                    break
                logger.warning("WS 오류, %ss 후 재연결: %s", backoff, e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle_real(self, items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            code = clean_code(item.get("item"))
            vals = item.get("values", {}) or {}
            price = to_int(vals.get("10"))  # FID 10 = 현재가
            if code and price:
                with self._lock:
                    self._prices[code] = price
                if self._on_tick:
                    try:
                        self._on_tick(code, price)
                    except Exception:
                        logger.exception("on_tick 콜백 오류 %s", code)

    def close(self) -> None:
        self._ws_stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

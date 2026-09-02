# 01 · Broker Adapter & 키움 REST 연동

> 증권사 독립 인터페이스(`BrokerAdapter`) + 키움 REST 구현체. **핵심 원칙: 전략 코드는 키움을 모른다.** 나중에 한투/토스로 바꿔도 이 파일들만 교체.

---

## ⚠️ 확정 스펙 표 (Phase 0에서 공식 문서·SDK로 실측해 채운다)

아래 값은 **구조/자리표시자**다. `openapi.kiwoom.com` 공식 가이드와 공식 SDK(`github.com/Kiwoom-Securities/Kiwoom-REST-API`)로 **실제 값을 확인**해 채운 뒤 코딩한다. 버전에 따라 도메인·TR·필드가 다를 수 있다.

> **실측 진행:** ✅=확정(2026-09-01, 공식 저장소 예제 + younghwan91/kiwoom-rest-api auth.py 소스로 확인) · ⬜=Phase 2에서 실측.

| 항목 | 모의(demo) | 실전(real) | 상태 |
|---|---|---|---|
| REST Base URL | `https://mockapi.kiwoom.com` | `https://api.kiwoom.com` | ✅ |
| WebSocket URL | `wss://mockapi.kiwoom.com:10000` | `wss://api.kiwoom.com:10000` | ✅ |
| 토큰 발급 endpoint | `POST /oauth2/token` | 동일 | ✅ |
| 토큰 요청 헤더 | `Content-Type: application/json;charset=UTF-8` | | ✅ |
| 토큰 요청 body | `{"grant_type":"client_credentials","appkey":<key>,"secretkey":<secret>}` (필드명 `secretkey`, appsecret 아님) | | ✅ |
| 토큰 응답 필드 | `token`, `token_type`, `expires_dt`(yyyyMMddHHmmss), `return_code`, `return_msg` | | ✅ |
| 토큰 만료 | `expires_dt` 값으로 확인 (스모크 테스트 실행 시 실측) | | ⬜ |
| 데이터 요청 공통 | `POST`, 헤더 `authorization: Bearer <token>` + `api-id: <TR>` + `Content-Type: application/json;charset=UTF-8`. (데이터 요청엔 appkey 헤더 불필요, 토큰만). 연속조회는 응답 헤더 `cont-yn`/`next-key` | | ✅ |
| 잔고조회 TR | `kt00018` (계좌평가잔고내역요청), path `/api/dostk/acnt`, body `{"qry_tp":"1"(합산)/"2"(개별),"dmst_stex_tp":"KRX"}`. 응답 합계 `prsm_dpst_aset_amt`(추정예탁자산)·`tot_evlt_amt`(총평가금액)·`tot_pur_amt`·`tot_evlt_pl`. 보유목록 `acnt_evlt_remn_indv_tot[]`: `stk_cd,stk_nm,rmnd_qty,pur_pric,cur_prc,evltv_prft` | | ✅ |
| 현재가 조회 TR | `ka10001` (주식기본정보요청), path `/api/dostk/stkinfo`, body `{"stk_cd"}`. 응답 현재가 `cur_prc` (부호 접두 가능 예 `"+57800"` → 절대값 파싱) | | ✅ |
| 호가 조회 TR | `ka10004` (주식호가요청), path `/api/dostk/mrkcond`, body `{"stk_cd"}` | | ✅ |
| 매수 TR | `kt10000`, path `/api/dostk/ordr`, body `{"dmst_stex_tp":"KRX","stk_cd","ord_qty","trde_tp","ord_uv","cond_uv"}`. `trde_tp`=`"3"`시장가/`"0"`지정가. `ord_uv`=주문단가(시장가는 `""`). 응답 `ord_no`(주문번호) | | ✅ |
| 매도 TR | `kt10001`, path/body 매수와 동일 | | ✅ |
| 취소 TR | `kt10003`, path `/api/dostk/ordr`, body `{"dmst_stex_tp":"KRX","orig_ord_no"(7자리),"stk_cd","cncl_qty"("0"=잔량전부)}` | | ✅ |
| 정정 TR | `kt10002` (패턴상 — MVP 미사용, 취소+재주문으로 대체) | | ⬜ |
| 미체결 조회 TR | `ka10075`, path `/api/dostk/acnt`, body `{"all_stk_tp","trde_tp","stex_tp","stk_cd"}`. 응답 `ord_no,oso_qty`(미체결수량)`,stk_cd` | | ✅ |
| 실시간 WebSocket | URL `wss://mockapi.kiwoom.com:10000/api/dostk/websocket`. LOGIN `{"trnm":"LOGIN","token":<access_token>}`(성공 `return_code==0`). PING 수신 시 **받은 프레임 그대로 echo**. 등록 `{"trnm":"REG","grp_no":"1","refresh":"1","data":[{"item":[codes],"type":["0B"]}]}`. 수신 `trnm:"REAL"` → `data[].{type,item,values}`, 체결타입 `"0B"`, 현재가 `values["10"]`·체결시간 `values["20"]` | | ✅ |
| 동시구독 한도 | `______` (Phase 2 라이브 실측 — 우선 watchlist 상한 관리) | | ⬜ |
| Rate limit | `______` 건/초 (공식 문서 확인 전 보수적 토큰버킷 5/s 적용) | | ⬜ |

> **출처/재현(2026-09-01 실측):** 공식 저장소 `Kiwoom-Securities/Kiwoom-REST-API` — `examples/국내주식/주문/{buy,sell,cancel}_domestic_stock*.py`, `종목정보/get_domestic_stock_info.py`, `계좌/{get_domestic_account_evaluation_balance,get_domestic_unfilled_orders}.py`, `실시간시세/subscribe_domestic_stock_trade_*.py` + Python 래퍼 `younghwan91/kiwoom-rest-api`(`auth.py`, `websocket.py`). Postman 컬렉션(306)도 참조.
> **국내 TR 경로 규칙:** 도메인별 path — 계좌=`/api/dostk/acnt`, 시세=`/api/dostk/mrkcond`, 종목정보=`/api/dostk/stkinfo`, 주문=`/api/dostk/ordr` — 에 `api-id` 헤더로 TR 지정(POST).
> 스모크 테스트: [`engine/tools/check_kiwoom_token.py`](../engine/tools/check_kiwoom_token.py). Phase 2 통합 테스트: [`engine/tools/it_kiwoom.py`](../engine/tools/it_kiwoom.py).

---

## 1. BrokerAdapter 인터페이스 (`broker/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Callable, Optional
from .models import Order, Position, Balance, Side, OrderType

class BrokerAdapter(ABC):
    """증권사 독립 계약. 전략 코드는 오직 이 인터페이스만 사용한다."""

    @abstractmethod
    async def connect(self) -> None:
        """인증(토큰 발급) + WebSocket 연결. 실패 시 예외."""

    @abstractmethod
    async def get_price(self, code: str) -> int:
        """현재가(원). 실시간 캐시 우선, 없으면 REST 조회."""

    @abstractmethod
    async def get_prices(self, codes: list[str]) -> dict[str, int]:
        """여러 종목 현재가 일괄."""

    @abstractmethod
    async def place_order(
        self, code: str, side: Side, qty: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[int] = None,
    ) -> Order:
        """주문 제출. 성공 시 broker_order_id 채워진 Order 반환."""

    @abstractmethod
    async def cancel(self, order: Order) -> None: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_balance(self) -> Balance: ...

    @abstractmethod
    async def subscribe_realtime(
        self, codes: list[str], on_tick: Callable[[str, int], None]
    ) -> None:
        """codes 실시간 체결가 구독. 틱마다 on_tick(code, price) 호출.
        내부에서 자동 재연결·재구독."""
```

편의 래퍼: `place_buy(...)`, `place_sell(...)` 은 `place_order(side=BUY/SELL)` 의 얇은 래퍼.

## 2. 데이터 모델 (`broker/models.py`)

```python
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Optional

class Side(str, Enum): BUY = "buy"; SELL = "sell"
class OrderType(str, Enum): MARKET = "market"; LIMIT = "limit"
class OrderStatus(str, Enum):
    PENDING="pending"; SUBMITTED="submitted"; PARTIAL="partial"
    FILLED="filled"; CANCELED="canceled"; REJECTED="rejected"

@dataclass
class Order:
    code: str; name: str; side: Side; qty: int
    order_type: OrderType; price: Optional[int]
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: Optional[str] = None
    filled_qty: int = 0; filled_price: Optional[int] = None
    reason: str = ""              # 전략상 주문 사유(진입/익절/손절/kill 등)
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None

@dataclass
class Position:
    code: str; name: str; qty: int; avg_price: int
    current_price: int = 0
    @property
    def pnl(self) -> int: return (self.current_price - self.avg_price) * self.qty
    @property
    def pnl_pct(self) -> float:
        return (self.current_price/self.avg_price - 1)*100 if self.avg_price else 0.0

@dataclass
class Balance:
    cash: int            # 주문가능현금
    equity: int          # 총평가금(현금+주식평가)
    stock_value: int     # 주식평가금
    updated_at: datetime
```

## 3. KiwoomRestBroker (`broker/kiwoom.py`) 설계

```python
class KiwoomRestBroker(BrokerAdapter):
    def __init__(self, app_key, secret, account_no, mode="demo"):
        self.base = REAL_BASE if mode=="real" else DEMO_BASE   # 표에서 확정
        self.ws_url = REAL_WS if mode=="real" else DEMO_WS
        self._token = None; self._token_exp = None
        self._prices: dict[str,int] = {}     # 실시간 캐시
        self._limiter = TokenBucket(rate=..., capacity=...)   # 표에서 확정
```

### 3.1 토큰 매니저
- `_ensure_token()`: 만료 60초 전이면 재발급. 매 요청마다 `_ensure_token()` 선호출.
- 토큰은 메모리 캐시(파일 저장 금지). 재시작 시 재발급.
- **주의:** 매 요청 재발급하면 차단됨 → 반드시 캐싱.

### 3.2 요청 공통
- 헤더: `authorization: Bearer <token>`, `api-id: <TR>`, `appkey`, `appsecret`(표에서 확정), `content-type: application/json;charset=UTF-8`.
- `_limiter.acquire()` 후 호출. 429/일시오류는 **지수백오프 재시도**(최대 N회).
- 응답 코드/메시지 검사 → 실패 시 `BrokerError` 계층 예외(`AuthError`, `OrderRejected`, `RateLimited`, `TransientError`).

### 3.3 주문
- `place_order`: 표의 매수/매도 TR로 POST. 시장가/지정가 구분. 응답의 주문번호를 `Order.broker_order_id` 에.
- 체결 확인: (a) WebSocket 체결통보 수신, 또는 (b) 체결/미체결 조회 TR 폴링. 우선 폴링으로 확실히 구현, 이후 WS 통보로 개선.
- **주문 전 sanity(호출측 risk.py에서):** 가격이 상·하한가 범위 내인지, 수량>0, 예수금 충분 등.

### 3.4 실시간 시세 (WebSocket)
- `connect()` 에서 WS 연결 → 로그인/인증 메시지(표) → watchlist 등록.
- 수신 틱 → `self._prices[code]=price` + `on_tick` 콜백.
- **자동 재연결:** 끊기면 백오프 후 재연결 + 재구독. `asyncio` Task로 상시 유지.
- 동시구독 한도 초과 방지: watchlist(후보+보유) 상한 관리, 초과 시 REST 폴백.

### 3.5 조회
- `get_positions()`/`get_balance()`: 잔고 TR 응답 → `Position`/`Balance` 매핑. 응답 필드명은 표 확정 후 매핑 함수로 격리.

## 4. 모의/실전 분리

- `KIWOOM_MODE=demo|real` (env). base URL·WS·키를 분기.
- **모의와 실전 App Key/Secret은 별개**. 절대 혼용 금지.
- 실전 전환은 docs/05의 체크리스트를 통과해야 함. 코드상 `mode="real"` 이면 risk.py가 보수적 한도를 **강제**.

## 5. 통합 테스트 (모의계좌, Phase 2 완료 기준)

`engine/tests/it_kiwoom.py`(수동 실행, 네트워크 필요):
1. `connect()` → 토큰 발급 성공.
2. `get_balance()` → 모의 예수금 확인.
3. `get_price("005930")` → 삼성전자 현재가.
4. 지정가 소량 매수 → `broker_order_id` 수신 → 체결/미체결 조회 → `cancel()` → 잔고 원복.
5. `subscribe_realtime(["005930"], cb)` → 10초간 틱 수신 로그.
6. WS 강제 종료 → 자동 재연결 확인.

> 실측으로 표를 채우기 전에는 이 파일을 스텁으로 두고, 표 확정 직후 구현한다.

## 6. 다른 증권사로의 확장

새 증권사 = `broker/<name>.py` 에 `BrokerAdapter` 구현체 1개 추가 + 팩토리에서 선택. 전략/relay/앱 **무변경**. (한투 KIS, 토스 등)

# 03 · 전략 명세 — 분석 · 진입/청산 · 리스크 · 백테스트

> breakZone 분석을 봇으로 이식하고, 그 위에 **매매 규칙**을 얹는다. 규칙은 파라미터화하며 **정확한 임계값은 사용자 확정 + 백테스트로 결정**한다(감으로 하드코딩 금지).

---

## 1. 분석 로직 (breakZone 이식 — 사실 그대로)

### 1.1 후보 수집
- KIND(`kind.krx.co.kr`) AJAX POST → **투자경고종목**(종목명, 지정일). KONEX 제외.
- 종목코드: 종목명 → FinanceDataReader 매핑(`ticker_mapping`).
- **해제판단일** = 지정일 **포함 10번째 매매일**(pykrx+holidays 캘린더).

### 1.2 가격/해제조건 계산 (`analysis/calculator.py` — 순수함수, 변경 없음)
- `T-5`, `T-15` 매매일 = 해제판단일 기준 역산.
- pykrx OHLCV(1회 조회, T-40~해제판단일)에서 종가 dict 구성.
- **Price①** = Close(T-5) × 1.60 (반올림)
- **Price②** = Close(T-15) × 2.00 (반올림)
- **Price③** = T-15~T-5 구간 종가 최고가(약 11매매일)
- **해제금액** = min(Price①, Price②, Price③)  ← None 은 제외
- **하락비율** = ROUND((해제금액 − 현재가) / 해제금액 × 100)
  - 양수 = 현재가 < 해제금액("이만큼 올라야 해제")
  - 0 = 동일, 음수 = 현재가가 이미 해제금액 초과
- 상태: `ok`(T-5 종가 조회됨) / `partial` / `pending`(T-5 종가 미확정 → 수동입력 대상) / `error`.

> breakZone 대시보드는 하락비율 ≤ 25% 행을 강조(`DROP_THRESHOLD`). 즉 **현재가가 해제금액에 근접하거나 초과한** 종목이 관심 대상이었다.

### 1.3 봇에서의 차이
- 대시보드는 on-demand 1회. 봇은 **장 시작 시 후보 수집 + N분 주기 재수집**, watchlist는 **실시간 시세**(키움 WS)로 갱신.
- 현재가 소스: 대시보드=네이버. 봇=키움 실시간(폴백 네이버). 해제금액용 과거종가는 pykrx 유지.
- 산출 `Candidate` 는 `candidates` 테이블과 1:1(docs/02 §2.3).

---

## 2. 매매 규칙 (파라미터화)

### 2.0 사용자 확정 전략 (2026-09-02, D-013) — 초안, 수치 전부 조절 가능
> breakZone은 "분석"만 했다. 매매 규칙은 **사용자 트레이딩 노하우**로 아래와 같이 정의한다.
> **모든 수치는 `settings`(앱에서 조절 가능). 임계값은 Phase 6 백테스트로 튜닝.**
> ⚠️ 일부 항목은 Claude 해석/기본값 — "확인필요" 표기. 개발하며 상세화(사용자 방침).

#### Envelope 지표 (신규 — 진입·청산에 사용)
- 일봉 종가 기준 이동평균 밴드. `MA = SMA(env_period)`, `상단 = MA×(1+env_band)`, `하단 = MA×(1−env_band)`.
- 파라미터 `env_period`=20, `env_band`=0.10(±10%) (2026-09-02 사용자 확정, 조절 가능).
- 과거종가는 pykrx로 조회(현재가 계산과 별개, candidates OHLCV 재사용 가능).

### 2.1 진입(매수) 규칙 (`strategy/rules.py::should_enter`)
순수 함수: `(candidate, price, env, position_state, settings, portfolio_ctx) -> EnterDecision`.

**E1 · 신규 진입** (모두 AND):
1. `entry_drop_min ≤ drop_ratio ≤ entry_drop_max` (기본 **30~40**: 현재가가 해제금액보다 30~40% 낮음)
2. `price < env_lower` (현재가가 envelope 하단 아래)
3. `price ≥ min_price` (기본 **1000원** — 저가주 필터, 조절 가능. 0=무제한. 신규·추가매수 공통)
4. `candidate.status == 'ok'`(신뢰가능) 이고 미보유, `positions_cnt < max_positions`
5. 리스크 통과(§3)
→ **분할매수**: 1회 매수액 = `per_stock_krw × entry_split_pct`(기본 100만 × **30%** = 30만). **누적 매수액이 `per_stock_krw`(종목당 총액)를 넘지 않도록 상한**(2026-09-02 확정) — 30%씩 사되 합계가 총액 도달 시 중단(약 3~4회). `max_entries` 는 보조 상한.

**E2 · 추가매수(물타기)** — 보유 중:
- `price ≤ avg_price × (1 − add_on_drop_pct)` (평단 대비 **5~10%** 하락, 기본 7%) 이고 `entries_done < max_entries`
- → 1회분(`per_stock_krw × entry_split_pct`) 추가매수. (사용자 수동 추가매수도 허용 — 자동 규칙과 별개로 앱에서)

### 2.2 청산(매도) 규칙 (`strategy/rules.py::should_exit`)
`(position, price, env, position_state, settings) -> ExitDecision(reason, portion)`:

**X1 · 분할익절 시작** (아직 분할매도 안 한 상태, AND):
1. `price > env_upper` (현재가가 envelope 상단 위)
2. `pnl_pct ≥ take_profit_pct` (기본 **15%**)
→ 보유수량의 `first_sell_portion`(기본 **50%**) 매도. `partial_sold=True`, 이후 고점 추적 시작.

**X2 · 하락 전량매도** — `partial_sold` 이후:
- `price ≤ peak_since_partial × (1 − post_sell_stop_pct)` (기본 **5%** 하락) → **잔량 전량매도**.
- 기준 = 분할매도 후 **고점**(트레일링). 2026-09-02 확정.

**X3 · 급등 전량매도** — `partial_sold` 이후:
- 현재가가 전일종가 대비 **+`limit_up_pct`%**(기본 29≈상한가, 조절 가능 예 28) 이상 → **잔량 전량매도**. `sell_all_on_limit_up`로 on/off.

**X4 · 강제** (최우선): kill-switch / `daily_max_loss` 도달 → 전량 시장가 청산.

> 전량매도 조건(X2·X3)의 수치·기준은 사용자가 조절 가능(예시로 적은 값).

### 2.2b 포지션 전략상태 (엔진 로컬 추적 — 브로커 잔고 외 추가)
분할매수/매도 규칙에 필요한 종목별 상태:
- `entries_done`(분할매수 횟수), `partial_sold`(첫 분할매도 여부), `peak_since_partial`(분할매도 후 고점).
- 봇 메모리 + Supabase(`positions` 확장 또는 별도)로 유지, 재시작 시 복원(브로커 잔고 기준 재구성).

### 2.3 신호(signal) 매핑 — 앱 표시용
후보/보유를 `none|watch|enter|hold|exit` 로 태깅해 `candidates.signal`·이벤트로 반영(앱에서 색상 강조).

---

## 3. 리스크 가드 (`strategy/risk.py`) — 절대 우회 금지

주문 직전 모든 주문이 통과해야 하는 검사(하나라도 실패 시 차단 + `risk_block` 이벤트):
- **1회 한도:** 주문금액 ≤ `per_trade_krw`.
- **보유수 상한:** 신규 진입 시 `positions_cnt < max_positions`.
- **현금 충분:** 매수금액 ≤ 주문가능현금.
- **일 손실 상한:** 당일 실현손실 ≥ `daily_max_loss_krw` 면 신규진입 중단(청산만 허용).
- **가격 sanity:** 지정가가 당일 상한가~하한가(±30%) 범위 내, 현재가 대비 과도한 이탈 차단.
- **중복주문 가드:** 동일 종목·방향 미체결 주문 존재 시 재주문 금지(디바운스).
- **수량 검증:** qty>0 정수.
- **모드 강제:** `mode='real'` 이면 실전 보수 한도(docs/05)를 강제 적용.

kill-switch: `running` 중 kill 명령/치명오류/일손실 초과(옵션) → **전량 시장가 청산 후 stopped**. 앱·서버 양쪽 트리거.

---

## 4. 매매 루프 (`strategy/engine.py` 의사코드)

```
async def tick():
    if state != running or not market_open: return heartbeat_only()
    settings = relay.load_settings()
    prices = broker/ws cache
    # 1) 청산 우선
    for pos in positions:
        d = should_exit(pos, prices[pos.code], settings, ctx)
        if d.exit and risk.ok_sell(pos, d):
            o = await broker.place_order(pos.code, SELL, pos.qty, ...); record(o, d.reason)
    # 2) 진입
    if settings.enabled and not daily_loss_hit:
        for c in candidates_sorted:
            d = should_enter(c, prices[c.code], settings, portfolio_ctx)
            if d.enter and risk.ok_buy(c, d):
                qty = size(d, settings, cash)
                o = await broker.place_order(c.code, BUY, qty, ...); record(o, "entry")
    # 3) 동기화
    await relay.upsert_positions(...); await relay.push_bot_state(...)
```
- 주기: 시세는 실시간, 규칙 평가는 tick 주기(예: 3~10초, 파라미터). 
- 체결 반영: 주문 후 체결조회/통보로 positions 갱신 → 재진입/재청산 판단에 반영.
- **동시성 주의:** breakZone은 pykrx 병렬화 시 hang → 후보수집(pykrx)은 순차 또는 executor 격리, 매매 tick과 분리된 주기로.

---

## 5. 백테스트 (`backtest/runner.py`)

목적: 진입/청산 파라미터 결정 + 전략 유효성 검증(실계좌 전 필수).
- **데이터:** pykrx 과거 OHLCV로 특정 기간 각 매매일의 경고주 후보를 재구성(당시 KIND 목록은 재현 어려움 → 지정일/해제판단일 기반 근사 또는 수집 로그 활용).
- **엔진:** 동일한 `rules.py`·`risk.py` 를 과거 시세에 적용(코드 재사용 = 실전과 동일 로직 보장).
- **산출:** 총수익률, MDD(최대낙폭), 승률, 거래수, 평균보유일, 파라미터별 성과표.
- **파라미터 스윕:** `entry_drop_*`, `take_profit/stop_loss`, `max_positions`, 보유기간을 그리드로 탐색.
- **주의(과최적화 경계):** in-sample/out-of-sample 분리, 슬리피지·수수료·세금·미체결 가정 반영, 결과를 맹신하지 말 것.

> 백테스트의 KIND 과거 재현이 어렵다면, 우선 **모의투자 전진검증(paper forward test)** 을 주 검증수단으로 삼고 백테스트는 보조로 둔다(Phase 6).

---

## 6. 파라미터 목록(설정 항목) — `settings` 테이블과 일치

| 파라미터 | 의미 | 기본값 |
|---|---|---|
| `enabled` | 자동매매 on/off | false |
| `mode` | demo/real | demo |
| `env_period` | envelope 이동평균 기간(일) | 20 |
| `env_band` | envelope 밴드 비율(±) | 0.10 |
| `entry_drop_min` | 진입 하락비율 하한 | 30 |
| `entry_drop_max` | 진입 하락비율 상한 | 40 |
| `min_price` | 최소 매수가(원, 이 미만 매수 안 함, 0=무제한) | 1000 |
| `per_stock_krw` | 종목당 총 투자예정액 | 1,000,000 |
| `entry_split_pct` | 1회 매수 비중(총액 대비) | 0.30 |
| `max_entries` | 최대 분할매수 횟수 | 4 |
| `add_on_drop_pct` | 추가매수 트리거(평단 대비 하락) | 0.07 (5~10%) |
| `max_positions` | 최대 보유종목수 | 5 |
| `take_profit_pct` | 분할익절 시작 수익률 % | 15 |
| `first_sell_portion` | 첫 분할매도 비중 | 0.50 |
| `post_sell_stop_pct` | 분할매도 후 하락 전량매도 기준 | 0.05 |
| `post_sell_stop_ref` | 위 기준점 | peak (분할매도후 고점) |
| `sell_all_on_limit_up` | 급등 전량매도 사용 on/off | true |
| `limit_up_pct` | 급등 전량매도 기준(전일종가 대비 %) | 29 |
| `daily_max_loss_krw` | 일 손실 상한 | 500,000 |
| `order_type` | 시장가/지정가 | limit(지정가) |
| `tick_seconds` | 규칙 평가 주기(초) | 5 |

> 신규 파라미터가 많아 `settings` 컬럼 대신 우선 **`settings.extra` jsonb** 에 담아 유연하게 운용(안정화되면 컬럼 승격). 앱 설정화면(Phase 5)에서 편집.

`extra jsonb` 로 트레일링/부분청산 등 확장 파라미터 수용.

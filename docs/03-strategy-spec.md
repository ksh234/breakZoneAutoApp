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

### ⚠️ 미확정: 진입/청산의 "정확한 조건과 임계값"은 사용자 트레이딩 노하우 + 백테스트로 확정해야 한다.
아래는 **엔진 골격과 placeholder 기본값**이다. breakZone은 "분석/모니터링"만 했고 **매매 트리거는 정의된 적이 없다.** Phase 6에서 반드시 사용자와 규칙을 확정하고 이 문서를 갱신한다.

### 2.1 진입 규칙 (`strategy/rules.py::should_enter`)
순수 함수: `(candidate, price, settings, portfolio_ctx) -> EnterDecision`.
placeholder 기본 조건(모두 AND):
1. `candidate.status in ('ok','partial')` 이고 `release_amount` 존재.
2. `entry_drop_min <= drop_ratio <= entry_drop_max`  ← **핵심 임계값, 백테스트로 결정.**
3. 오늘이 해제판단일 관련 유효 구간(예: 해제판단일 이전 K매매일 이내) ← 파라미터.
4. 미보유 종목이고 `positions_cnt < max_positions`.
5. 리스크 통과(§3).
→ 매수수량 = `floor(min(per_trade_krw, cash) / price)`, 지정가/시장가 정책(파라미터).

### 2.2 청산 규칙 (`strategy/rules.py::should_exit`)
`(position, price, settings, today_ctx) -> ExitDecision(reason)`:
1. **익절:** `pnl_pct >= take_profit_pct`.
2. **손절:** `pnl_pct <= stop_loss_pct`.
3. **시간청산:** 보유가 해제판단일 도달 or D+N 경과(파라미터).
4. **트레일링/부분청산:** (선택, 확장) `extra` 파라미터.
5. **강제:** kill-switch / daily_max_loss 도달 시 전량.

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

| 파라미터 | 의미 | 기본(placeholder) |
|---|---|---|
| `enabled` | 자동 진입 on/off | false |
| `mode` | demo/real | demo |
| `entry_drop_min/max` | 진입 하락비율 구간 | **미정(백테스트)** |
| `per_trade_krw` | 1회 매수금액 | 1,000,000 |
| `max_positions` | 최대 보유종목수 | 5 |
| `take_profit_pct` | 익절 % | 10 |
| `stop_loss_pct` | 손절 % | -5 |
| `daily_max_loss_krw` | 일 손실 상한 | 500,000 |
| `hold_days_max` / 진입 유효구간 K | 보유/진입 타이밍 | 미정 |
| `order_type` | 시장가/지정가 | 미정 |
| `tick_seconds` | 규칙 평가 주기 | 5 |

`extra jsonb` 로 트레일링/부분청산 등 확장 파라미터 수용.

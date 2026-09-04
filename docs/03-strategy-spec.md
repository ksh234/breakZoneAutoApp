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
0. **매수 유효구간:** 오늘 ≤ 해제일 (해제일이 지난 D+ 종목은 신규·추가매수 제외 — 매수 적기는 T-5~해제일). 보유분은 계속 청산 관리. (2026-09-03)
1. `drop_ratio ≥ entry_drop_pct` (기본 **30**: 현재가가 해제금액보다 30% 이상 낮은 **매수구간**. 많이 떨어질수록 대상 — 상한 없음)
1-b. **저가 반등**(`entry_rebound_pct`>0일 때): 매수구간 진입 후 추적한 **저점 대비 `entry_rebound_pct` 이상 상승**해야 매수(급락 중 매수 방지, falling-knife 회피). 0이면 즉시(반등 안 봄). 저점은 매수구간에 있는 동안 갱신, 구간 벗어나면 리셋. (2026-09-03)
2. `price < env_lower` (현재가가 envelope 하단 아래)
3. `price ≥ min_price` (기본 **1000원** — 저가주 필터, 조절 가능. 0=무제한. 신규·추가매수 공통)
4. `candidate.status == 'ok'` — **값 확정 게이트**: 해제금액·하락비율이 정확하려면 T-5·T-15·최고가·현재가가 **모두** 있어야 함. 하나라도 없으면(pending/partial) 신규·추가매수 금지. (2026-09-03 사용자 규칙). 봇은 현재가를 키움으로 채운 뒤 status 재계산 → 다 갖춰지면 ok.
5. 미보유이고 `positions_cnt < max_positions`
6. 리스크 통과(§3)
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

**X2b · 2차 상승 전량매도** — `partial_sold` 이후 (2026-09-04 사용자 추가):
- 현재가 ≥ `partial_sell_price × (1 + post_sell_gain_pct/100)` → **잔량 전량매도**. 기준은 **1차(분할) 매도가**(평단 아님). `post_sell_gain_pct`=0 이면 끔(기본). 상한가(X3)와 별개로 목표 상승률에서 확정.
- 분할매도 후 판정 우선순위: **X3 상한가 → X2b 2차 상승 → X2 트레일링.**

**X3 · 급등 전량매도** — `partial_sold` 이후:
- 현재가가 전일종가 대비 **+`limit_up_pct`%**(기본 29≈상한가, 조절 가능 예 28) 이상 → **잔량 전량매도**. `sell_all_on_limit_up`로 on/off.

**X4 · 강제** (최우선): kill-switch(앱/서버 트리거) → 전량 시장가 청산.

> 전량매도 조건(X2·X3)의 수치·기준은 사용자가 조절 가능(예시로 적은 값).

### 2.2b 포지션 전략상태 (엔진 로컬 추적 — 브로커 잔고 외 추가)
분할매수/매도 규칙에 필요한 종목별 상태:
- `entries_done`(분할매수 횟수), `partial_sold`(첫 분할매도 여부), `peak_since_partial`(분할매도 후 고점), `partial_sell_price`(1차 매도가 — X2b 기준, 2026-09-04).
- **영속화(2026-09-03 구현):** 봇 메모리 + Supabase `strategy_state`(owner, code) 테이블. 저장 시점 = 매수 체결 접수·분할매도·고점 갱신·**매수구간 저점(`zone_low`) 변경** 시(변경분만). 청산 완료(잔고에서 사라짐)·저점 리셋 시 행 삭제. 봇 시작(LIVE 전환) 시 `restore_state()` 로 복원 → 재배포/재시작해도 분할 횟수·고점·저점 유지. 복원 실패 시 빈 상태로 시작(기존 보유는 잔고 기준 1회 매수로 간주).

### 2.3 신호(signal) 매핑 — 앱 표시용
후보/보유를 `none|watch|enter|hold|exit` 로 태깅해 `candidates.signal`·이벤트로 반영(앱에서 색상 강조).

---

## 3. 리스크 가드 (`strategy/risk.py`) — 절대 우회 금지

주문 직전 모든 주문이 통과해야 하는 검사(하나라도 실패 시 차단 + `risk_block` 이벤트):
- **종목당 한도:** 누적 매수액 ≤ `per_stock_krw` (1회 매수 = `per_stock_krw × entry_split_pct`).
- **보유수 상한:** 신규 진입 시 `positions_cnt < max_positions`.
- **현금 충분:** 매수금액 ≤ 주문가능현금.
- **평가손실 한도:** 보유 전체 **평가손실(미실현)** ≥ `max_unrealized_loss_krw` 면 신규진입 중단(청산만 허용). 하락장에서 물타기 폭증 방지. (실현손실 기준은 손절매가 없는 이 전략에선 무의미 → 미실현 기준으로 결정, 2026-09-02)
- **가격 sanity:** 지정가가 당일 상한가~하한가(±30%) 범위 내, 현재가 대비 과도한 이탈 차단.
- **중복주문 가드:** 동일 종목·방향 미체결 주문 존재 시 재주문 금지(디바운스).
- **수량 검증:** qty>0 정수.
- **모드 강제:** `mode='real'` 이면 실전 보수 한도(docs/05)를 강제 적용.

kill-switch: `running` 중 kill 명령/치명오류 → **전량 시장가 청산 후 stopped**. 앱·서버 양쪽 트리거. (평가손실 한도는 kill이 아니라 신규매수 중단만)

---

## 4. 매매 루프 (`strategy/engine.py` — 실제 구현, 동기)

`main.py` 가 `tick_seconds` 주기로 `engine.tick()` 호출:
```
def tick():                              # 동기(D-011)
    if status != running or not market_open: return heartbeat_only()
    sync_positions()                     # 브로커 잔고 → positions + Supabase 반영
    pending = {u.code for u in broker.get_unfilled_orders()}   # 중복주문 방지
    # 1) 청산 우선 (보유마다)
    for pos in positions:
        price = broker.get_price(pos.code)        # 키움 WS 캐시 우선, 없으면 REST
        d = should_exit(pos.qty, pos.avg_price, price, envelope[code], params, state[code], at_limit_up)
        if d.exit and code not in pending and risk.ok_sell(...):
            broker.place_order(code, SELL, d.qty, ...); relay.insert_order(...); day_realized_pnl += ...
    # 2) 진입 (자동매매 ON 이고 평가손실 한도 미도달)
    if params.enabled and unrealized_pnl() > -max_unrealized_loss_krw:
        for cand in candidates:
            price = broker.get_price(cand.code)
            d = should_enter(cand.drop_ratio, cand.status, price, envelope, params, state, holding, ...)
            if d.enter and code not in pending and risk.ok_buy(..., unrealized_pnl=..., prev_close=...):
                broker.place_order(code, BUY, d.qty, ...); relay.insert_order(...); state.on_buy(...)
    # 3) 동기화
    relay.push_bot_state(status, market_open, equity, cash, day_pnl, positions_cnt)   # 하트비트
```
- **enabled / 보유 관리:** `enabled` 는 **신규·추가 매수만** on/off. **청산(exits)은 running 이면 항상 평가** → 경고 해제로 후보에서 빠진 보유 종목도 계속 청산 관리(positions 기준, envelope·시세도 보유 종목에 대해 유지). 완전 정지=stop(status), 전량청산=kill. 후보는 refresh 때 현재 경고주 목록에 없으면 삭제(prune)되지만 **positions 는 유지**된다.
- **후보/지표 갱신:** `refresh()` 가 별도 주기(`REFRESH_SEC`=10분, 장중)로 KIND 수집 + 종목별 envelope/전일종가(pykrx) 계산 + 키움 WS 재구독.
- **명령 처리:** `relay.start_command_listener` 폴링 스레드가 `commands`(start/stop/pause/resume/kill/set_param/close_position)를 1.5초 주기로 수신→`engine.handle_command`.
- **현재가:** 키움 실시간(WS 캐시)+REST 폴백. 과거종가(envelope·해제금액)는 pykrx.
- **동시성 주의:** breakZone은 pykrx 병렬화 시 hang → 후보수집(pykrx)은 순차. 매매 tick과 분리된 주기(refresh).

---

## 5. 백테스트 (`backtest/runner.py`)

목적: 진입/청산 파라미터 결정 + 전략 유효성 검증(실계좌 전 필수).
- **데이터:** pykrx 과거 OHLCV로 특정 기간 각 매매일의 경고주 후보를 재구성(당시 KIND 목록은 재현 어려움 → 지정일/해제판단일 기반 근사 또는 수집 로그 활용).
- **엔진:** 동일한 `rules.py`·`risk.py` 를 과거 시세에 적용(코드 재사용 = 실전과 동일 로직 보장).
- **산출:** 총수익률, MDD(최대낙폭), 승률, 거래수, 평균보유일, 파라미터별 성과표.
- **파라미터 스윕:** `entry_drop_pct`, `env_period`/`env_band`, `take_profit_pct`, `first_sell_portion`, `post_sell_stop_pct`, `limit_up_pct`, `max_entries` 등을 그리드로 탐색.
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
| `entry_drop_pct` | 진입 하락비율 기준(이 % 이상 하락 시 매수) | 30 |
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
| `post_sell_gain_pct` | 분할매도 후 **1차 매도가 대비** 상승 전량매도 %(0=끔) | 0 |
| `sell_all_on_limit_up` | 급등 전량매도 사용 on/off | true |
| `limit_up_pct` | 급등 전량매도 기준(전일종가 대비 %) | 29 |
| `max_unrealized_loss_krw` | 보유 평가손실 한도(이상이면 신규매수 중단) | 500,000 |
| `order_type` | 시장가/지정가 | limit(지정가) |
| `tick_seconds` | 규칙 평가 주기(초) | 5 |

> 신규 파라미터가 많아 `settings` 컬럼 대신 우선 **`settings.extra` jsonb** 에 담아 유연하게 운용(안정화되면 컬럼 승격). 앱 설정화면(Phase 5)에서 편집.

`extra jsonb` 로 트레일링/부분청산 등 확장 파라미터 수용.

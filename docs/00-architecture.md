# 00 · 시스템 아키텍처

> 전체 그림, 구성요소 책임, 데이터 흐름, 통신 패턴. 코딩 전에 이 문서로 "무엇이 어디서 도는가"를 확정한다.

## 1. 구성요소와 책임

### A. 전략엔진 (Python 봇) — `engine/`
장중 상시 구동되는 핵심. 세 가지 일을 한다.
1. **분석(Analysis):** KIND 크롤링 → 경고주 목록 → pykrx 과거종가 + 실시간 시세로 해제금액·하락비율 계산 → **후보(candidate) 산출**. (breakZone 로직 재사용)
2. **매매(Trading):** 후보/보유에 진입·청산 규칙 적용 → 리스크 가드 통과분만 **키움 REST로 (모의)주문**. 체결/포지션 추적.
3. **동기화(Relay):** 상태·후보·포지션·주문·이벤트를 **Supabase로 push**, 앱의 **명령을 realtime 구독**해 실행.

내부 레이어(의존 방향은 위→아래로만):
```
main.py (스케줄러/상태기계)
  └─ strategy/engine.py (오케스트레이션)
       ├─ analysis/*      (후보 산출 — 외부: KIND/pykrx/naver)
       ├─ broker/*        (주문/시세 — 외부: 키움 REST/WS)
       ├─ strategy/rules,risk (순수 규칙 — 외부 의존 0)
       └─ relay/*         (상태 동기화 — 외부: Supabase)
```
`strategy/rules.py`·`analysis/calculator.py` 는 **순수 함수**(외부 의존 0) → 100% 단위테스트. breakZone의 3-layer(Domain/Adapter/Route) 철학을 그대로 계승.

### B. Supabase — 상시 중계 계층
- **Postgres:** 상태·이력의 단일 진실원(SSOT).
- **Realtime:** 테이블 변경을 WebSocket으로 앱에 push, 명령을 봇에 push.
- **Auth:** 앱 로그인(단일 사용자).
- **Edge Function(선택):** 백그라운드 푸시 채택 시(Phase 5-B), 중요 이벤트 → FCM 발송. 미채택이면 불필요.
- 봇·앱의 **유일한 접점**. 둘은 서로의 주소를 모른다. **다른 백엔드(Firebase 등)를 별도로 두지 않는다** — 푸시가 필요할 때만 FCM을 transport로 빌려 쓴다.

### C. Flutter 앱 — `app/`
읽기(모니터링) + 쓰기(제어명령/설정)만. 매매 로직 없음("봇을 켜는 게 아니라 지켜보는" 역할). Supabase Realtime 구독으로 실시간 표시 + 인앱 알림(`events`), `commands`/`settings` 쓰기로 제어. (백그라운드 푸시는 선택 — Phase 5-B에서 FCM 추가 시.)

### D. 키움 REST API — 외부
실제(모의) 주문·체결·시세. 봇의 `broker/kiwoom.py` 만 이걸 안다. 나머지 코드는 `BrokerAdapter` 인터페이스만 본다.

## 2. 데이터 흐름 (장중 1 사이클)

```
① 후보 갱신
   KIND 크롤링 ─▶ 경고주[] ─▶ (pykrx 과거종가 + 실시간 시세) ─▶ Candidate[]
   Candidate[] ─▶ Supabase.candidates (upsert)

② 청산 평가 (보유 포지션마다)
   Position + 시세 ─▶ rules.should_exit? ─▶ risk 통과 ─▶ broker.place_sell
   ─▶ orders/positions 갱신 ─▶ Supabase 반영 + event(체결)

③ 진입 평가 (미보유 후보마다)
   Candidate + 시세 ─▶ rules.should_enter? ─▶ risk 통과 ─▶ broker.place_buy
   ─▶ orders/positions 갱신 ─▶ Supabase 반영 + event(진입)

④ 하트비트
   bot_state(status, equity, cash, positions_count, ts) ─▶ Supabase (주기적)

⑤ 명령 처리 (비동기, 항상)
   Supabase.commands INSERT ─(realtime)▶ 봇 handler ─▶ 실행 ─▶ command.status 갱신
```

후보 목록(KIND)은 하루 단위로 거의 안 바뀌므로 **장 시작 시 1회 + N분 주기**로 갱신하고, **시세**는 watchlist(후보+보유)에 대해 WebSocket 실시간 또는 짧은 주기로 갱신한다.

## 3. 통신 패턴 — outbound-only (이관 용이성의 핵심)

```
[봇]  ──HTTPS/WSS──▶  [키움 API]      (나가기만)
[봇]  ──HTTPS/WSS──▶  [Supabase]      (나가기만: state push + commands 구독)
[앱]  ──HTTPS/WSS──▶  [Supabase]      (나가기만)
```
- 봇은 **어떤 인바운드 연결도 받지 않는다** → 공유기 NAT/유동 IP/방화벽 뒤에서도 동작, 포트포워딩 불필요, 공격면 최소.
- 앱은 봇의 IP를 모른다 → 봇이 집이든 클라우드든 무관.
- **결과:** "클라우드 이관 = 봇 프로세스만 이동". 앱·Supabase·규약 불변. (자세히: docs/06)

## 4. 상태 기계 (봇)

```
stopped ──start──▶ running ──stop──▶ stopping ──▶ stopped
running ──pause──▶ paused ──resume──▶ running
running/paused ──kill──▶ (전량 시장가 청산) ──▶ stopped
any ──fatal error──▶ error(자동정지+알림)
```
- `running`: 장중 매매 루프 활성.
- `paused`: 신규 진입 중단, 보유 청산 규칙은 유지(선택). 
- `kill`: 긴급. 전량 청산 후 stopped. 앱·서버 양쪽에서 트리거 가능.
- 장 시간 밖에서는 `running`이어도 주문 없이 idle + 하트비트.

## 5. 시간·시장 규칙

- 타임존 **KST(UTC+9)** 고정. 모든 타임스탬프 KST ISO.
- 정규장 09:00–15:30. 매매 루프는 이 구간만. (시간외/동시호가 정책은 docs/03에서 결정)
- 매매일 캘린더는 breakZone `kind_fetcher`의 pykrx+holidays 로직 재사용.

## 6. 기술 스택 요약

| 영역 | 선택 | 비고 |
|---|---|---|
| 봇 | Python 3.11+, asyncio | 시세 WS + 명령 구독 동시성 |
| 크롤/분석 | requests, beautifulsoup4, pykrx, finance-datareader, holidays | breakZone 그대로 |
| 브로커 | 키움 REST/WebSocket | docs/01 |
| DB/중계 | Supabase(Postgres, Realtime, Edge Functions/Deno) | docs/02 |
| 앱 | Flutter, Riverpod, supabase_flutter, fl_chart (+ 선택: firebase_messaging) | docs/04 |
| 배포 | Docker, 국내 VPS 또는 AWS/GCP 서울 | docs/06 |

## 7. 동시성 모델 (봇)

`asyncio` 단일 이벤트 루프 권장:
- Task 1: 매매 루프(주기 tick).
- Task 2: 키움 WebSocket 시세 수신 → 최신가 캐시.
- Task 3: Supabase commands 구독 → 명령 큐.
- Task 4: 하트비트.
- pykrx/requests(동기)는 `run_in_executor`로 감싸 블로킹 회피. (breakZone은 순차처리로 pykrx hang을 피했음 — 병렬화 시 주의: docs/03)

공유 상태(포지션·설정·상태기계)는 단일 루프 내 소유로 락 최소화. 외부 명령은 큐로 직렬화.

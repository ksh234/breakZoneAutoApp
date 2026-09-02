# breakZoneAutoApp — 경고주 자동매매 시스템 마스터 로드맵

> **이 문서 하나로 새 PC / 새 세션에서 바로 시작할 수 있도록 작성된 자립형(self-contained) 로드맵 + 설계 문서.**
> 세부 설계는 `docs/` 하위 문서로 분리했고, 각 Phase에서 필요한 문서를 링크로 가리킨다.
> 먼저 이 문서를 처음부터 끝까지 읽고, `docs/00-architecture.md` 를 본 뒤 Phase 0 부터 순서대로 진행한다.
> **실시간 진행 상태는 [`PROGRESS.md`](PROGRESS.md), 결정 근거는 [`DECISIONS.md`](DECISIONS.md).**

---

## 진행 현황 (2026-09-02)

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 환경·계정·키움 스펙 실측 | ✅ 완료 (토큰 발급·잔고 실증) |
| 1 | 분석 로직 이식 → 후보 산출 | ✅ 완료 (경고주 22종목 라이브) |
| 2 | 키움 Broker Adapter(모의) | ✅ 코드+읽기 실증 (왕복주문은 장중 1회 대기) |
| 3 | Supabase 스키마·중계 | ✅ 완료 (라이브 검증) |
| 4 | 전략 엔진(규칙·리스크·루프) | ✅ 코드 완료 (장중 라이브 운용 대기) |
| 5 | Flutter 앱(모니터링·제어·설정) | ✅ 코드+로그인·실시간 실증 (5-B FCM 보류) |
| 6 | 백테스트·모의 검증 | ⬜ 다음 |
| 7 | 실계좌 전환 | ⬜ 신중히 |
| 8 | 클라우드 이관 | ⬜ 마지막 |

**코드 규모:** 봇(engine) Python — analysis/broker/relay/strategy + 테스트 **132개 통과**. 앱(app) Flutter — 7화면, analyze 클린·빌드 성공. 커밋 22개.
**남은 라이브 확인:** ① 키움 왕복주문(`it_kiwoom.py --order`, 장중) ② 봇 하루 모의 운용(`python -m src.main`, 장중).

---

## 0. 한 문단 요약

기존 `breakZone`(KRX 투자경고종목을 크롤링·분석하는 Flask 대시보드)의 **분석 로직을 재사용**하여, 클라우드/집-PC에서 24시간(또는 장중) 상시 구동되는 **자동매매 봇**을 만든다. 봇은 **키움 REST API**로 (처음엔 모의투자) 주문·체결하고, 상태를 **Supabase**에 올린다. 사용자는 **Flutter 앱**으로 어디서나 모니터링하고 봇을 원격 제어(시작/중지/긴급청산/파라미터 변경)한다. 봇은 바깥으로 나가는(outbound) 연결만 사용하므로 집 공유기(NAT)·유동 IP 환경에서도 동작하고, 나중에 **봇 프로세스만 클라우드로 옮기면** 이관이 끝난다.

```
[전략엔진 (Python 봇) — 집 Windows PC → 나중에 클라우드]
   │  ①분석: KIND 크롤링 + pykrx 과거종가 + 실시간시세
   │  ②매매: 키움 REST API 로 (모의)주문·체결
   │  ③동기화: Supabase 로 상태 push / 명령 subscribe   ← 모두 outbound
   ▼
[Supabase — 상시 중계 계층: Postgres + Realtime + Auth (+ 선택: Edge Function 푸시)]
   ▲
   │  실시간 구독(읽기) / 제어명령(쓰기)
[Flutter 앱 — 모니터링 & 원격제어]
```

---

## 1. 확정된 핵심 결정 (변경 시 이 표부터 갱신)

| 항목 | 결정 | 근거 / 메모 |
|---|---|---|
| 증권사 API | **키움 REST API** (`openapi.kiwoom.com`) | 미래에셋은 개인 자동매매 오픈API 미제공. 키움 REST는 OAuth 토큰·국내주식 주문·**모의투자**·WebSocket 실시간 지원, OCX 불필요(리눅스/클라우드 이관 용이). 공식 SDK: `github.com/Kiwoom-Securities/Kiwoom-REST-API` |
| 매매 범위 (1단계) | **모의투자부터** | 실제 자금 위험 차단. 검증 후 단계적 실계좌 전환(§Phase 7). |
| 앱 | **Flutter** (Android 우선, iOS 확장 가능) | 단일 코드베이스, Supabase 라이브러리 성숙 |
| 중계/백엔드 | **Supabase (단독)** | Postgres + Realtime(WebSocket) + Auth + Edge Function. 무료 티어로 시작. 봇·앱의 유일한 접점. **다른 백엔드(Firebase 등) 없이 이것만 사용** |
| 봇 호스팅 | **집 Windows PC(간헐 구동) → 나중에 클라우드 VM** | 봇은 outbound-only → NAT/유동IP 무관. 이관 = 프로세스 이동 |
| 봇 언어 | **Python 3.11+** | breakZone 로직 재사용 |
| 푸시(백그라운드 알림) | **1단계 제외 — Supabase Realtime(인앱)만.** 백그라운드 푸시(FCM)는 **Phase 5에서 추가 여부 결정** | 앱이 열려 있을 때의 실시간 알림은 Realtime으로 충분. 잠금화면/종료 상태 알림이 필요할 때만 FCM 추가 |

### ⚠️ 계좌 관련 중요 사실
봇은 **키움 계좌**에서 거래한다. 사용자가 현재 쓰는 미래에셋 MTS로는 봇의 포지션을 볼 수 없다. 실전 전환 시 **키움 계좌 개설 + 키움 REST API 사용 신청**이 필요하다. 모니터링은 (a) 우리 Flutter 앱 또는 (b) 키움 영웅문 MTS로 한다.

---

## 2. 문서 지도 (docs/)

| 문서 | 내용 | 주로 쓰는 Phase |
|---|---|---|
| [docs/00-architecture.md](docs/00-architecture.md) | 시스템 구성요소, 데이터 흐름, 통신 패턴(outbound-only), 리포지토리 구조 | 전체 |
| [docs/01-broker-kiwoom.md](docs/01-broker-kiwoom.md) | 키움 REST 인증·주문·시세 스펙, `BrokerAdapter` 인터페이스, 모의/실전 분리 | Phase 0, 2 |
| [docs/02-supabase-schema.md](docs/02-supabase-schema.md) | DB 테이블 전체 DDL, RLS 정책, Realtime, (선택) Edge Function 푸시 | Phase 3, 5 |
| [docs/03-strategy-spec.md](docs/03-strategy-spec.md) | 분석 로직 이식, 진입/청산 규칙(파라미터화), 리스크 한도, 백테스트 | Phase 1, 4, 6 |
| [docs/04-flutter-app.md](docs/04-flutter-app.md) | 앱 화면·상태관리(Riverpod)·Realtime 구독·제어 흐름 (푸시는 선택) | Phase 5 |
| [docs/05-security-risk.md](docs/05-security-risk.md) | 시크릿 관리, kill-switch, 리스크 가드, 실계좌 전환 체크리스트 | Phase 4, 7 |
| [docs/06-deployment.md](docs/06-deployment.md) | 집 PC 구동(서비스/작업스케줄러), Docker화, 클라우드 이관 | Phase 0, 8 |

---

## 3. 리포지토리 최종 구조 (목표 형상)

```
breakZoneAutoApp/
├── ROADMAP.md                     ← 이 문서
├── README.md
├── docs/                          ← 설계 문서 7종
├── engine/                        ← Python 전략 엔진(봇)
│   ├── requirements.txt
│   ├── .env.example
│   ├── src/
│   │   ├── main.py                # 엔트리: 스케줄러 루프 + 명령 구독
│   │   ├── config.py              # 환경변수 로드
│   │   ├── analysis/              # breakZone 이식 (순수+어댑터)
│   │   │   ├── calculator.py      #  ← breakZone/src/calculator.py 그대로
│   │   │   ├── kind_fetcher.py    #  ← breakZone/src/fetchers/kind_fetcher.py
│   │   │   ├── pykrx_fetcher.py
│   │   │   ├── naver_fetcher.py
│   │   │   ├── ticker_mapping.py
│   │   │   └── candidates.py      # 경고주 → 후보 스냅샷 산출 (app.py 로직 이식)
│   │   ├── broker/
│   │   │   ├── base.py            # BrokerAdapter (ABC)
│   │   │   ├── kiwoom.py          # KiwoomRestBroker
│   │   │   └── models.py          # Order/Position/Balance dataclass
│   │   ├── strategy/
│   │   │   ├── engine.py          # 진입/청산 평가 오케스트레이션
│   │   │   ├── rules.py           # 순수 규칙 함수 (테스트 가능)
│   │   │   └── risk.py            # 리스크 한도, kill-switch
│   │   ├── relay/
│   │   │   └── supabase_client.py # 상태 push, commands subscribe
│   │   └── backtest/
│   │       └── runner.py
│   └── tests/
├── app/                           ← Flutter 앱 (flutter create 산출물)
│   └── lib/ ...
├── supabase/
│   ├── migrations/                # SQL 스키마 마이그레이션
│   ├── functions/                 # Edge Functions (선택: push-notify — Phase 5에서 결정)
│   └── config.toml
└── infra/
    ├── Dockerfile                 # engine 컨테이너화 (클라우드 이관용)
    └── docker-compose.yml
```

`breakZone/` 폴더는 **그대로 유지**(분석 검증/참조용). 엔진은 breakZone 코드를 `engine/src/analysis/` 로 **복사·이식**하고, 이후 독립적으로 관리한다(양쪽을 동기화하려 하지 말 것 — 이식 시점 스냅샷으로 고정).

---

## 4. Phase별 로드맵

각 Phase는 **목표 / 선행조건 / 작업 / 산출물 / 완료 기준(Acceptance)** 으로 구성. 순서대로 진행하며, 각 Phase 끝의 완료 기준을 통과해야 다음으로 넘어간다. 규모 표기: 🟢작음 🟡보통 🔴큼.

---

### Phase 0 — 환경 구축 & API 스펙 확정 🟡
**목표:** 새 PC에서 개발 가능한 상태 + 외부 계정/키 확보 + 키움 실제 스펙 확정.

> ✅ **실행용 체크리스트: [`PHASE0-CHECKLIST.md`](PHASE0-CHECKLIST.md)** — 사용자 직접 절차(키움·Supabase·런타임)와 진행 상황을 여기서 관리한다.

**작업**
1. **폴더 이동:** `breakZone/`, `breakZoneAutoApp/` 를 새 PC로 복사. (git 미사용 상태 → Phase 0 말미에 `git init` 권장)
2. **런타임 설치:** Python 3.11+, Flutter SDK(+Android Studio/SDK), Node.js LTS(Supabase CLI용), Git.
3. **계정/키 발급**
   - 키움: 계좌 개설 → [openapi.kiwoom.com](https://openapi.kiwoom.com/) REST API 사용 신청 → **모의투자용** App Key/Secret 발급.
   - Supabase: 프로젝트 생성 → `SUPABASE_URL`, `anon key`, `service_role key` 확보.
   - (Firebase/FCM는 **Phase 0에서 불필요.** 백그라운드 푸시를 쓸지 Phase 5에서 결정 후, 채택 시 그때 생성.)
4. **🔴 키움 실제 스펙 대조 확정** (이 로드맵의 값은 "구조"이며 정확한 값은 버전에 따라 다름):
   - 모의/실전 **base URL(도메인·포트)** 확인.
   - 접근토큰 발급 엔드포인트·요청/응답 필드·**만료시간**.
   - 국내주식 **주문(매수/매도/정정/취소) api-id(TR)** 와 요청/응답 스키마.
   - 잔고·체결 조회 TR.
   - 실시간 시세 **WebSocket** 접속·구독 메시지 형식·**동시구독 한도**.
   - **호출한도(rate limit)** 수치.
   - 확정값을 [docs/01-broker-kiwoom.md](docs/01-broker-kiwoom.md) 의 "확정 스펙" 표에 채워 넣는다.
   - 참고: 공식 SDK `github.com/Kiwoom-Securities/Kiwoom-REST-API`(Python 예제 362개, Postman 컬렉션) 를 클론해 실제 요청을 재현.

**산출물:** 개발환경, 발급된 키 목록(§secrets), 채워진 키움 스펙 표.

**완료 기준**
- [ ] `python --version` 3.11+, `flutter doctor` 통과, `supabase --version` 동작
- [ ] 키움 모의투자 App Key/Secret 로 **접근토큰 발급 성공**(curl/Postman로 1회 확인)
- [ ] 키움 모의계좌 **잔고조회 200 응답** 확인
- [ ] Supabase 프로젝트에 접속(대시보드) + CLI 로컬 링크 완료
- [ ] docs/01 "확정 스펙" 표의 모든 칸이 실제 값으로 채워짐

---

### Phase 1 — 전략 엔진 코어 (분석 로직 이식 + 후보 산출) 🟡
**목표:** breakZone 분석을 라이브러리로 이식하고, "경고주 후보 스냅샷"을 산출하는 순수 서비스 완성. (아직 주문·Supabase 없음)

**작업**
1. `engine/` 스캐폴딩(`requirements.txt`, `.env.example`, `src/`, `tests/`).
2. breakZone 이식: `calculator.py`, `kind_fetcher.py`, `pykrx_fetcher.py`, `naver_fetcher.py`, `ticker_mapping.py` 를 `engine/src/analysis/` 로 복사. import 경로만 수정.
3. `analysis/candidates.py`: breakZone `app.py` 의 `_compute_stock_row` 로직을 이식해 **후보 리스트**(dataclass `Candidate`)를 반환하는 순수 함수 `build_candidates()` 작성. 반환 필드는 docs/02 `candidates` 테이블과 1:1 매핑.
4. breakZone 의 pytest 를 이식·통과(모든 외부 I/O mock).

**산출물:** `python -m engine.src.analysis.candidates` 실행 시 현재 경고주 후보를 콘솔에 출력.

**완료 기준**
- [x] `build_candidates()` 라이브 동작(경고주 22종목 산출). breakZone 과 동일 로직 이식(값 일치) — 대시보드 직접 스팟체크는 사용자 확인 여지
- [x] 이식된 단위테스트 전부 통과 (68개, 2026-09-01)
- [x] 네트워크 실패 시 종목별 격리(하나 실패해도 나머지 산출) 동작 확인 (test_candidates + 라이브 pending/partial 처리)

---

### Phase 2 — Broker Adapter + 키움 REST 연동(모의투자) 🔴
**목표:** 증권사에 독립적인 `BrokerAdapter` 인터페이스와 키움 구현체 완성. 모의계좌로 시세조회·주문·잔고 전 기능 동작.

**작업** (상세: [docs/01-broker-kiwoom.md](docs/01-broker-kiwoom.md))
1. `broker/base.py`: `BrokerAdapter` 추상클래스 정의(§계약).
2. `broker/models.py`: `Order`, `Position`, `Balance`, enum(`Side`, `OrderType`, `OrderStatus`).
3. `broker/kiwoom.py`: `KiwoomRestBroker`
   - 토큰 매니저(발급·캐싱·만료 전 자동 재발급).
   - `get_price/get_prices`(REST 시세), `place_buy/place_sell/cancel`, `get_positions/get_balance`.
   - `subscribe_realtime(codes, on_tick)`: WebSocket 구독(자동 재연결).
   - 레이트리미터(토큰버킷) + 재시도(지수백오프).
   - `KIWOOM_MODE=demo|real` 로 base URL·키 분기.
4. 통합 테스트(모의계좌): 소량 지정가 매수 → 체결/미체결 조회 → 취소 → 잔고 확인.

**산출물:** 모의계좌에서 왕복 주문 시나리오를 재현하는 스크립트/테스트.

**완료 기준**
- [ ] 접근토큰 자동 발급·만료 재발급 동작
- [ ] 임의 종목 현재가 조회 정확
- [ ] 모의 매수 주문 → 주문번호 수신 → 체결/취소 확인
- [ ] `get_positions()`·`get_balance()` 가 키움 모의 잔고와 일치
- [ ] WebSocket 실시간 체결가 수신(끊김 시 자동 재연결)
- [ ] 전략 코드가 키움 세부사항을 전혀 몰라도 되도록 인터페이스가 캡슐화됨

---

### Phase 3 — Supabase 스키마 & 봇 동기화(outbound) 🟡
**목표:** DB 스키마 확정, 봇이 상태를 push 하고 앱 명령을 realtime 으로 구독. 통신 경로 완성.

**작업** (상세: [docs/02-supabase-schema.md](docs/02-supabase-schema.md))
1. `supabase/migrations/` 에 테이블 DDL 작성·적용: `settings`, `bot_state`, `candidates`, `positions`, `orders`, `events`, `commands`. (`devices` 테이블은 푸시 채택 시 Phase 5에서 추가)
2. RLS 정책(단일 사용자) + 봇은 `service_role` 로 접근.
3. Realtime publication 활성화(구독 대상 테이블).
4. `relay/supabase_client.py`:
   - `push_bot_state()`, `upsert_candidates()`, `upsert_positions()`, `insert_order()`, `insert_event()`.
   - `subscribe_commands(handler)`: `commands` 테이블 INSERT 를 realtime 으로 수신 → 핸들러 호출 → 처리결과 status 갱신.
   - 하트비트(주기적 `bot_state` 갱신).
   - 연결 끊김 재연결·오프라인 버퍼링.

**산출물:** 봇 실행 시 Supabase 대시보드에서 `bot_state` 하트비트가 갱신되고, 수동으로 `commands` 행을 넣으면 봇이 로그로 반응.

**완료 기준**
- [x] 모든 테이블·RLS·Realtime 적용됨 (마이그레이션 3종, 2026-09-02 라이브 확인)
- [x] 봇이 outbound 연결만으로 state push 성공 (check_supabase.py: 하트비트·후보·이벤트 upsert 확인)
- [~] `commands` INSERT → 봇 수신 (폴링 1.5초 구현, `--listen` 실증은 사용자 선택 확인)
- [ ] 네트워크 끊김 후 자동 재연결 + 밀린 상태 재전송 (오프라인 버퍼는 후속 — Phase 4/8에서 보강)

---

### Phase 4 — 전략 엔진 매매 루프(모의 자동매매) 🔴
**목표:** 분석→신호→(모의)주문→포지션관리→동기화의 자동 루프 완성. 리스크 가드·kill-switch 포함.

**작업** (상세: [docs/03-strategy-spec.md](docs/03-strategy-spec.md), [docs/05-security-risk.md](docs/05-security-risk.md))
1. `strategy/rules.py`: 진입/청산 **순수 규칙 함수**(파라미터 입력 → 결정 출력). ⚠️ 정확한 임계값은 사용자 확정 + 백테스트 필요 — 기본값은 placeholder.
2. `strategy/risk.py`: `MAX_POSITIONS`, `PER_TRADE_KRW`, `DAILY_MAX_LOSS`, 중복주문 가드, 가격 sanity(상·하한가 범위), kill-switch.
3. `strategy/engine.py`: 오케스트레이션
   - 후보 갱신(장 시작/주기) + watchlist 실시간 시세 구독.
   - 보유 포지션 청산 평가 → 후보 진입 평가 → 리스크 통과분만 주문.
   - 주문/체결/포지션 변화 → Supabase 반영, 중요 이벤트 발행.
4. `main.py`: KST 장중 스케줄러(09:00–15:30) + 장외 idle + `commands` 구독(start/stop/kill/set_param/close_position).
5. 상태기계: `stopped → running → (paused) → stopping`; kill 시 전량청산 후 stop.

**산출물:** 모의계좌로 하루 자동 운용되는 봇.

**완료 기준**
- [x] 규칙 함수 단위테스트 통과(경계값 포함) — test_strategy 29 + test_engine 6 (2026-09-02)
- [x] 앱 명령(start/stop/kill/set_param)에 봇이 반응 — handle_command 단위검증(라이브 실증 대기)
- [x] 리스크 한도 초과 시 주문 차단 로그·이벤트 — ok_buy/ok_sell + risk_block 이벤트
- [x] kill-switch → 전량 시장가 청산 + stopped — kill() 단위검증
- [ ] 하루 모의 운용 후 orders/positions/events Supabase 일관 기록 — **장중 라이브 검증 대기**

---

### Phase 5 — Flutter 앱(모니터링 & 원격제어) 🔴
**목표:** 어디서나 봇 상태를 실시간으로 보고 제어한다. (기본은 **Supabase Realtime 인앱 알림**만; 백그라운드 푸시는 아래 5-B에서 선택)

**작업 (5-A · 필수 — Supabase 단독)** (상세: [docs/04-flutter-app.md](docs/04-flutter-app.md))
1. `flutter create app` + 패키지(`supabase_flutter`, `flutter_riverpod`, `fl_chart` 등).
2. 인증(Supabase 이메일/비번, 단일 사용자).
3. 화면
   - **대시보드:** 봇 상태 카드(running/stopped·하트비트 경과·평가금·현금·당일손익), 보유 포지션, 후보 리스트(하락비율 정렬·신호 강조), 최근 주문.
   - **제어:** Start/Stop 토글, **긴급 정지(kill-switch)**, 설정(파라미터 편집 → `settings` 쓰기).
   - **이벤트/알림 이력:** `events` 실시간 구독(인앱 배너 + 목록).
   - (반자동 확장용) 승인 대기 주문 화면.
4. Realtime 스트림 구독 → UI 자동 갱신. 모든 제어는 `commands`/`settings` 쓰기로만.

**작업 (5-B · 선택 — 백그라운드 푸시 결정 지점)**
- **여기서 결정:** 앱을 내려놓은 상태(잠금화면/종료)에서도 체결·손절 등 알림을 받을 것인가?
  - **불필요하면** → 5-B 전체 스킵. Supabase Realtime만으로 완료(앱 열려 있을 때 알림).
  - **필요하면** → FCM 추가: Firebase 프로젝트 생성 → `firebase_core`/`firebase_messaging` + `google-services.json`, `devices` 테이블 마이그레이션 추가, Supabase Edge Function `push-notify`(`events` severity high/critical → FCM 발송), 앱에서 토큰 등록·수신·딥링크. (상세: docs/04 §6, docs/02 §6 — "선택" 표기 부분)

**산출물:** 실기기에서 봇을 모니터링/제어하는 앱(디버그 빌드).

**완료 기준**
- [x] 로그인(Supabase Auth) + RLS 하 본인 데이터 표시 (2026-09-02 실증)
- [x] 대시보드 봇 상태 실시간 반영 (Realtime 스트림)
- [x] 제어 화면 Start/Stop/Pause/Kill(2단계) → `commands` insert (봇 반응은 장중 라이브 대기)
- [x] 설정 화면 15개 파라미터 그룹별 편집 → `settings.extra` 저장
- [x] 후보/포지션/주문/이벤트 실시간 목록
- [~] 봇 실제 반응(Start→running, kill→청산 등)은 장중 봇 구동 시 실증
- [ ] (5-B) 백그라운드 푸시(FCM) — 미채택(보류)

---

### Phase 6 — 백테스트 & 페이퍼 검증 🟡
**목표:** 전략 파라미터를 데이터로 확정하고, 모의계좌로 충분히 운용해 신뢰 확보.

**작업**
1. `backtest/runner.py`: pykrx 과거 데이터로 경고주 후보를 재구성하고 규칙을 적용해 성과(수익률/MDD/승률/거래수) 산출.
2. 파라미터 스윕으로 진입·청산 임계값 후보 도출 → 사용자와 최종 규칙 확정.
3. 모의계좌 **2~4주 이상** 무인 운용 + 로그/이벤트 리뷰(슬리피지·미체결·오류율).

**완료 기준**
- [ ] 백테스트 성과표 산출 + 재현 가능
- [ ] 사용자 확정 규칙이 docs/03 에 반영
- [ ] 모의 운용 기간 동안 치명적 버그 0, 리스크 한도 정상 작동

---

### Phase 7 — 안전장치 강화 & 실계좌 전환 준비 🔴 (실제 자금 — 신중)
**목표:** 실계좌로 넘어가기 전 모든 안전장치·운영절차 완비.

**작업** (상세: [docs/05-security-risk.md](docs/05-security-risk.md))
1. 실전 전환 체크리스트 이행(금액 상한 축소, 하루 손실 상한, 종목/1회 한도, 이중 확인 UI).
2. 장애 대응: 봇 다운/네트워크 단절/주문 거부/부분체결 시나리오 문서화·자동 알림.
3. 시크릿 관리 점검(실전 키는 OS 키체인/Windows 자격증명, .env 커밋 금지).
4. **소액 실계좌**로 카나리 운용 → 단계적 한도 상향.

**완료 기준**
- [ ] `KIWOOM_MODE=real` 전환 시 안전 한도가 강제됨
- [ ] 모든 실패 시나리오에 알림/자동 정지 매핑
- [ ] 소액 실전에서 모의와 동일 동작 확인
- [ ] 롤백/긴급중지 절차가 앱·서버 양쪽에서 검증됨

---

### Phase 8 — 클라우드 이관 🟡
**목표:** 봇을 집 PC에서 상시 클라우드로 이전(상시성·안정성 확보).

**작업** (상세: [docs/06-deployment.md](docs/06-deployment.md))
1. `infra/Dockerfile` 로 엔진 컨테이너화(pykrx/네트워크 의존성 포함).
2. 국내 VPS 또는 AWS/GCP(서울 리전) VM에 배포. 시크릿은 환경변수/시크릿매니저.
3. 프로세스 관리(systemd/컨테이너 재시작 정책) + 로그 수집 + 하트비트 모니터.
4. 집 PC ↔ 클라우드 **동시 구동 방지**(같은 계좌 이중 주문 방지 락 — docs/05).

**완료 기준**
- [ ] 클라우드에서 봇이 무중단 구동(재부팅 자동복구)
- [ ] 앱/Supabase 무변경으로 그대로 연동
- [ ] 이중 실행 방지 락 동작

---

## 5. 통신 규약 요약 (왜 이관이 쉬운가)

- 봇은 **오직 outbound**: 키움 API(HTTPS/WSS) + Supabase(HTTPS/WSS) 로 나가기만 한다. 인바운드 포트 개방·공인 IP·포트포워딩 **불필요**.
- 앱은 **오직 Supabase** 와만 통신. 봇 주소를 몰라도 된다.
- 제어는 앱이 `commands`/`settings` 에 **쓰고**, 봇이 realtime 으로 **구독**해 실행 → 결과를 다시 DB에 기록.
- 따라서 "클라우드 이관 = 봇 프로세스만 이동". 앱·Supabase·통신 규약은 불변.

---

## 6. 시크릿 목록 (절대 커밋 금지 — .env / OS 키체인)

| 키 | 용도 | 보관 |
|---|---|---|
| `KIWOOM_APP_KEY` / `KIWOOM_SECRET` (demo/real 각각) | 키움 인증 | engine `.env`(개발), 실전은 OS 키체인 |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | 봇→DB(쓰기) | engine `.env` |
| `SUPABASE_ANON_KEY` | 앱→DB | Flutter(공개 가능, RLS로 보호) |
| Firebase `google-services.json` / 서비스계정 | FCM 푸시 — **선택(Phase 5-B 채택 시에만)** | 앱 / Edge Function 시크릿 |

`.gitignore` 에 `.env`, `*.local`, `google-services*.json`, 키 파일 포함(§Phase 0).

---

## 7. 리스크 & 원칙 (반드시 지킬 것)

1. **모의투자로 충분히 검증하기 전 실제 자금 절대 금지.** (Phase 6 통과 필수)
2. **모든 자동 주문에 리스크 가드**(1회 한도·보유수 상한·일 손실 상한·가격 sanity·중복주문 방지).
3. **kill-switch는 앱·서버 양쪽에서 즉시 동작**(전량청산 + 정지).
4. **같은 계좌 이중 실행 금지**(집 PC/클라우드 동시 구동 방지 락).
5. **시크릿은 코드/깃에 넣지 않는다.**
6. 전략 임계값은 **감이 아니라 백테스트로** 정하고, 실전은 소액 카나리부터.
7. 장애(네트워크·주문거부·부분체결)는 **조용히 넘어가지 말고** `events`(인앱 알림, 채택 시 푸시)로 알린다.

---

## 8. 다음 세션 시작 방법 (새 PC)

1. 이 `ROADMAP.md` 를 처음부터 끝까지 읽는다.
2. `docs/00-architecture.md` 로 전체 그림을 확인한다.
3. **Phase 0** 부터 순서대로 진행. 각 Phase 완료 기준 체크박스를 모두 통과한 뒤 다음으로.
4. 키움 스펙은 반드시 **공식 문서/공식 SDK로 실측**해 docs/01 표를 채운 뒤 코딩한다.
5. 막히면 해당 Phase가 가리키는 docs/ 문서를 본다.

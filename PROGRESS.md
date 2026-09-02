# 진행 상황 (PROGRESS) — breakZoneAutoApp

> **새 세션은 이 파일을 가장 먼저 읽는다.** "지금 어디까지 왔고, 다음에 무엇을 하는가"의 단일 출처(SSOT).
> 이 프로젝트는 **로드맵 Phase 단위로 세션을 나눠** 진행한다. 매 세션 끝에 이 파일의 §다음 할 일 · §세션 로그를 갱신한다.
>
> **읽는 순서(신규 세션):** ① 이 파일(PROGRESS) → ② [ROADMAP.md](ROADMAP.md) → ③ 현재 Phase가 가리키는 [docs/](docs/) → ④ [DECISIONS.md](DECISIONS.md)(왜 그렇게 정했나) → ⑤ [PHASE0-CHECKLIST.md](PHASE0-CHECKLIST.md)(환경/계정 진행 상태)

---

## 🧭 한눈에 (현재 상태)

| 항목 | 값 |
|---|---|
| **마지막 업데이트** | 2026-09-02 |
| **현재 Phase** | **Phase 0~3 완료** → Phase 4(전략 엔진) 준비 |
| **코드 상태** | analysis + broker + relay + config + 마이그레이션. 테스트 91개. Supabase 중계 **라이브 검증 완료**. |
| **다음 마일스톤** | Phase 4 — 매매 루프 + ⭐사용자 매매조건 확정(D-008). candidates 현재가 키움 배선(D-005) |
| **블로커** | 없음. (남은 확인: 키움 왕복주문 `it_kiwoom.py --order` 장중 1회 — Phase 4와 병행 가능) |

---

## ▶️ 다음에 할 일 (바로 착수 지점)

**사용자(🙋) — 지금 바로: 키움 연결 확인 (Phase 0 마지막 게이트)**
```powershell
cd engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # .env 에 모의 App Key/Secret/계좌번호 입력
python tools/check_kiwoom_token.py
```
→ "✅ 접근토큰 발급 성공" 나오면 Phase 0 핵심 게이트 통과. (결과를 다음 세션에 알려주면 됨)
- (병행 가능) [supabase.com](https://supabase.com) 프로젝트 생성(Seoul) → URL·anon·service_role 확보.

**사용자(🙋) 할 일 — 두 가지 (순서 무관):**

*(A) Supabase 연결 (Phase 3 라이브 검증)*
1. `SUPABASE_URL`(Settings>Data API>Project URL) / **secret key**(`sb_secret_…`, service_role 대체) / 사용자 UID(`SUPABASE_OWNER_UUID`) → `engine\.env`(`SUPABASE_SECRET_KEY`)
2. 마이그레이션 적용: 대시보드 **SQL Editor** 에 `supabase/migrations/0001_init.sql` → `0002_rls.sql` → `0003_realtime.sql` 순서로 붙여넣고 각각 Run
3. 확인: `.\.venv\Scripts\python.exe tools\check_supabase.py` → "중계 동작 확인" + 대시보드 Table editor 에 bot_state/candidates/events 행 생성

*(B) 키움 왕복주문 (Phase 2 완료 게이트) — 평일 장중(09:00~15:30)*
```powershell
cd engine
.\.venv\Scripts\python.exe tools\it_kiwoom.py --order
```
→ "주문번호 → 미체결 → 취소 완료" 나오면 Phase 2 완료.

**그다음 — Phase 4 (전략 엔진 매매 루프, 🤝 ⭐):**
- `strategy/rules.py`(진입/청산 규칙) + `risk.py`(리스크가드·kill-switch) + `engine.py`(오케스트레이션) + `main.py`(스케줄러·상태기계)
- ⭐ 여기서 **사용자의 자동매수/매도 조건**을 함께 확정(Claude가 후보 항목 메뉴 제시 → 사용자 선택). D-008.
- candidates 현재가 소스를 네이버→키움 실시간으로 배선(D-005).

**미결:**
- 키움 정정 TR(kt10002) 미검증(취소+재주문으로 대체 가능).

**재현:**
```powershell
cd engine
.\.venv\Scripts\python.exe -m pytest -q                     # 테스트 91개
.\.venv\Scripts\python.exe -m src.analysis.candidates       # 경고주 후보
.\.venv\Scripts\python.exe tools\it_kiwoom.py               # 브로커 읽기전용
.\.venv\Scripts\python.exe tools\check_supabase.py          # 중계(키 입력 후)
```

---

## ✅ 완료한 일 (요약)

- [x] 설계 문서 7종(docs/00~06) + ROADMAP 통독·분석
- [x] Phase 0 체크리스트 작성([PHASE0-CHECKLIST.md](PHASE0-CHECKLIST.md))
- [x] 문서 관리 체계 수립(PROGRESS/DECISIONS)
- [x] **Python 3.12.10 설치**(winget, 사용자 범위, PATH 등록)
- [x] Flutter 기존 설치 확인(`D:\dev\flutter` v3.47.2 — 재설치 불필요)
- [x] 키움 "REST API MCP" 정체 조사(공식 저장소에 MCP 추가됨 — 아래 결정 참조)
- [x] 키움 계좌 개설 + 모의투자 참가 + 모의 App Key/Secret/계좌번호 확보(사용자)
- [x] 키움 모의 스펙 실측 → docs/01 확정 스펙 표 반영(토큰·잔고·base URL)
- [x] git 초기화 + 첫 커밋(e3913f8)
- [x] engine Phase 0 스캐폴딩 + 키움 연결 스모크 테스트 작성
- [x] 키움 모의 접근토큰 발급 성공(Phase 0 게이트)
- [x] **Phase 1: breakZone 분석 로직 이식 + `build_candidates()` 라이브 후보 산출(22종목) + 테스트 68개 통과**
- [x] **Phase 2: 키움 스펙 실측 + `broker/`(BrokerAdapter+KiwoomRestBroker) 구현 + 읽기전용 라이브 검증 + 테스트 85개** (왕복주문 실증은 사용자 대기)
- [x] **Phase 3: Supabase 마이그레이션(7테이블+RLS+Realtime) + `relay/`(Relay 중계) + config + 테스트 91개 + 라이브 검증 완료** ✅

---

## 🗂 세션 로그 (최신 → 과거)

### 세션 2026-09-02 (Phase 3 Supabase 중계 코드 ✅)
- **결정:** D-012 = 명령 수신 폴링(스레드, 1.5초), Realtime 후속.
- **마이그레이션:** `supabase/migrations/` 0001_init(7테이블)·0002_rls·0003_realtime.
- **엔진:** `src/config.py`(env 중앙화, SUPABASE_* 추가), `src/relay/supabase_client.py`(Relay: ensure_singletons·push_bot_state·upsert_candidates/positions·insert_order/event·load_settings·start_command_listener 폴링·ack_command). requirements 에 supabase 추가, .env.example 에 SUPABASE_OWNER_UUID.
- **테스트:** test_relay.py(supabase 클라이언트 mock, 페이로드 검증) — **총 91개 통과.**
- **도구:** `tools/check_supabase.py`(스모크: 싱글턴·하트비트·후보 upsert·이벤트·명령 리스너).
- **라이브 검증 완료(2026-09-02):** 사용자가 마이그레이션 3종 적용 + `.env`(secret key/URL/owner) 입력 후 `check_supabase.py` 성공 — 싱글턴·하트비트·후보 upsert·이벤트·settings 로드 전부 OK. 봇↔Supabase 경로 완성.
- **키 체계:** Supabase 신규 secret key(`sb_secret_…`) 사용. `SUPABASE_URL` 은 base 만(코드가 /rest/v1 자동 제거).
- **사용자 가이드 제공:** Supabase 프로젝트 생성·키 확보·auth 사용자(owner UID) 생성·SQL Editor 마이그레이션 적용 절차.

### 세션 2026-09-02 (Phase 2 브로커 코어 ✅)
- **키움 스펙 실측 완료** → docs/01 표 채움: 주문 kt10000(매수)/kt10001(매도)/kt10003(취소) path `/api/dostk/ordr`(body dmst_stex_tp/stk_cd/ord_qty/trde_tp/ord_uv, trde_tp 3=시장/0=지정), 현재가 ka10001 `/api/dostk/stkinfo`(cur_prc), 잔고 kt00018(acnt_evlt_remn_indv_tot[]), 미체결 ka10075, WebSocket `/api/dostk/websocket`(LOGIN token→REG 0B→REAL, PING echo).
- **결정:** D-007=자체구현(kiwoom-client 참조), D-011=동기 REST + 스레드 WebSocket.
- **구현:** `engine/src/broker/` — errors.py, models.py(Order/Position/Balance/enums), base.py(BrokerAdapter 동기), kiwoom.py(KiwoomRestBroker: 토큰관리·레이트리밋·재시도·주문/잔고/현재가/미체결·WS 스레드), __init__.py(create_broker 팩토리).
- **테스트:** test_broker.py 신규(순수유틸+HTTP mock 주문/잔고/현재가/취소/실시간파싱). **총 85개 통과.**
- **라이브 검증(읽기전용, 사용자 .env):** `it_kiwoom.py` → 토큰OK, 잔고 5천만(모의), 현재가 005930=250,500 조회 성공. 왕복주문(--order)은 사용자 실행 예정.
- **미결:** candidates 현재가 네이버→키움 교체는 Phase 4 배선. 정정 TR 미검증.

### 세션 2026-09-01 (Phase 1 분석 로직 이식 완료 ✅)
- **이식:** breakZone `src/calculator.py` + `fetchers/{kind,pykrx,naver}_fetcher.py` + `ticker_mapping.py` → `engine/src/analysis/`. import 경로만 수정(`from src.fetchers` → `from .`; kind_fetcher 의 미사용 `config` import 제거). 이식 시점 스냅샷으로 고정(양방향 동기화 안 함).
- **신규:** `analysis/candidates.py` — `Candidate` dataclass(docs/02 매핑) + `build_candidates()`(app.py `_compute_stock_row` 이식, 종목별 격리) + 콘솔 출력(`python -m src.analysis.candidates`).
- **테스트:** calculator/naver/pykrx/kind 테스트 이식 + `test_candidates.py` 신규. breakZone 원본 테스트의 stale 참조(`_n_business_days_after`) → 실제 함수 `_kth_business_day_on_or_after` 로 조정. **68개 전부 통과.**
- **라이브 검증:** venv에 Phase1 deps 설치(pandas/pykrx/fdr/bs4/holidays) 후 실행 → **경고주 22종목** 후보 산출 성공(해제금액·현재가·하락비율·상태). breakZone 대시보드와 동일 로직(값 일치).
- **환경 메모:** 실행은 `engine/.venv/Scripts/python.exe` 직접 호출(실행정책으로 activate 미사용). pykrx의 "KRX 로그인 실패"는 선택적 자격증명 경고(무관).
- **남은 것(Phase 1 관점):** 현재가 소스는 아직 네이버(이식본). Phase 2에서 키움 실시간으로 교체.

### 세션 2026-09-01 (Phase 0 게이트 통과 ✅)
- 사용자가 `.env`에 모의 키 입력 후 `python tools/check_kiwoom_token.py` 실행 → **"접근토큰 발급 성공"** 확인. 키움 모의 REST 연결 실증.
- venv 활성화는 실행정책으로 실패했으나 전역 Python(3.12)에 deps 설치되어 그대로 실행됨. (Phase 1부터 venv 권장 — 실행정책 `Set-ExecutionPolicy -Scope Process RemoteSigned` 후 활성화)
- → **Phase 0 핵심 게이트 통과. Phase 1(분석 로직 이식) 착수 가능.**

### 세션 2026-09-01 (이어서 — Phase 0 스캐폴딩)
- **키움 스펙 실측:** 공식 저장소 예제 + younghwan91/kiwoom-rest-api `auth.py` 소스로 확정 →
  모의 REST `https://mockapi.kiwoom.com`, WS `wss://mockapi.kiwoom.com:10000`; 토큰 `POST /oauth2/token`
  body `{grant_type:"client_credentials", appkey, secretkey}`(필드명 secretkey), 응답 `token/token_type/expires_dt`;
  잔고 `kt00018` path `/api/dostk/acnt`; 호가 `ka10004` path `/api/dostk/mrkcond`. → docs/01 표 반영.
- **git 초기화:** `git init -b main` + 첫 커밋(e3913f8). 로컬 identity 설정(ksh234).
- **engine Phase 0 스캐폴딩:** `.env.example`, `requirements.txt`(requests/dotenv), `tools/check_kiwoom_token.py`(토큰+잔고 스모크), `README.md`. `.gitignore`에 `.env.example` 예외 추가.
- **사용자 진행:** 모의 App Key/Secret + 모의계좌번호 확보 완료.
- **남은 것:** 사용자가 `.env` 채우고 스모크 테스트 실행 → "토큰 발급 성공" 확인(Phase 0 마지막 게이트).

### 세션 2026-09-01 (환경 준비)
- **Python 설치:** winget으로 Python 3.12.10 사용자 범위 설치. pip 25.0.1. User PATH 1순위 등록(Store 스텁보다 우선) → 새 터미널에서 `python` 정상. 설치 경로 `C:\Users\ksh23\AppData\Local\Programs\Python\Python312\`.
- **Flutter:** `D:\dev\flutter`에 v3.47.2(stable, Dart 3.13.2) 이미 존재. PATH 미등록뿐 → 재설치 불필요. Phase 5 전 PATH 등록만.
- **키움 MCP 조사:** 사용자가 "8/27 REST API MCP" 언급. 확인 결과 **공식 저장소([Kiwoom-Securities/Kiwoom-REST-API](https://github.com/Kiwoom-Securities/Kiwoom-REST-API))에 MCP 서버(`mcp_exec/`,`mcp_spec/`) 추가**됨. 이 저장소가 337개 API 스펙 + Postman(306) + `kiwoomcli` + 주문 예제 + 모의 지원을 포함 → docs/01 실측의 권위 원본. **결정: MCP는 봇 매매경로가 아니라 개발 보조**(→ DECISIONS D-006). Python 래퍼 후보 `kiwoom-client`([younghwan91/kiwoom-rest-api](https://github.com/younghwan91/kiwoom-rest-api)) 발견(주문·WS·async·토큰갱신·is_mock, MIT, 스타0) → Phase 2 갈림길로 기록(D-007).
- **문서 체계:** 세션 간 인수인계용 PROGRESS.md + DECISIONS.md 도입.

### 세션 2026-08-31
- **분석:** ROADMAP + docs/00~06 전체 통독. 현재 상태 실측(코드 0줄, breakZone src ~1540줄, git 미초기화).
- **Phase 0 체크리스트** 작성 + ROADMAP에 링크.
- **로컬 환경 점검:** Git 있음, Python은 MS Store 스텁만(실제 미설치), Node/Supabase CLI/Docker 없음.
- **현재가 소스 확정:** 네이버 → 키움 실시간 WS(폴백 네이버), 과거종가는 pykrx 유지(D-005).
- **작업 순서 합의:** 순차 진행. 사용자는 외부 절차 직접 수행하며 학습, Claude는 키 불필요 작업 담당.

---

## 🔀 주요 결정 요약 (상세·근거는 [DECISIONS.md](DECISIONS.md))

| # | 결정 | 상태 |
|---|---|---|
| D-001~004 | 증권사=키움 REST / 앱=Flutter / 중계=Supabase 단독 / 봇=Python. 백그라운드 푸시(FCM) 1단계 제외 | ✅ 확정(ROADMAP §1) |
| D-005 | 현재가 소스: 키움 실시간 WS(폴백 네이버), 과거종가 pykrx 유지 | ✅ 확정 |
| D-006 | 키움 MCP 서버는 **개발 보조**(스펙 실측·수동조회)용. **봇 매매경로는 REST/WS 직접 호출** | ✅ 확정 |
| D-007 | Phase 2 브로커 구현: 자체구현 vs `kiwoom-client` 래핑 | ⏳ 보류(Phase 2에서 결정) |
| D-008 | 자동매매 "조건" 항목/수치는 Phase 4에서 함께 확정, 앱에서 조절(Phase 5) | ⏳ 예정 |
| D-009 | 문서 관리: PROGRESS/DECISIONS로 세션 간 인수인계 | ✅ 확정 |

---

## 💻 환경 현황 (2026-09-01)

| 런타임 | 상태 | 위치/버전 | 필요 Phase |
|---|---|---|---|
| Python | ✅ | 3.12.10 (`...\Programs\Python\Python312`) | 1+ |
| Git | ✅ | 2.55.0 | 0+ |
| Flutter | ✅ (PATH 미등록) | `D:\dev\flutter` 3.47.2 | 5 |
| Node + Supabase CLI | ❌ | — | 3 |
| Docker | ❌ | — | 8 |

**폴더:** `breakZone/`(참조·수정금지) 와 `breakZoneAutoApp/`(작업) 형제 배치. 이식은 스냅샷 복사.

---

## 📌 열려있는 질문 / 보류

- **자동매매 조건(진입/청산)의 구체 항목·수치** — 미정. Phase 4에서 Claude가 후보 항목 메뉴 제시 → 사용자 조합. 수치는 Phase 6 백테스트로 튜닝. (D-008)
- **Phase 2 브로커 라이브러리 선택** — 자체구현 vs kiwoom-client. Phase 2 착수 시 결정. (D-007)
- **백그라운드 푸시(FCM)** — Phase 5-B에서 채택 여부 결정.
- **git init 실행 시점** — 사용자 "시작" 신호 대기 중.

---

## 🔧 세션 종료 시 갱신 규칙 (Claude용 메모)

매 세션 끝에 반드시:
1. §한눈에 표의 날짜·현재 Phase 갱신
2. §다음에 할 일 최신화
3. §세션 로그에 이번 세션 항목 추가(무엇을·왜·결과)
4. 새 결정이 있으면 §결정 요약 표 + DECISIONS.md 추가
5. 관련 체크리스트(PHASE0-CHECKLIST 등) 체크박스 갱신

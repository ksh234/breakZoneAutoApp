# Phase 0 체크리스트 — 환경 구축 & API 스펙 확정

> [`ROADMAP.md`](ROADMAP.md) Phase 0의 **실행용 체크리스트**. 항목을 완료하면 `[ ]` → `[x]` 로 바꾸며 순차 진행한다.
> 원칙: **모의(demo)부터**. 실전 키·Firebase는 여기서 다루지 않는다(Phase 5-B / Phase 7).

## 진행 상황 요약
- 착수일: 2026-08-31 · **Phase 0 완료(2026-09-01 게이트 통과), 잔여 항목 2026-09-03 현행화**
- 미완: A-6(약관·rate limit 수치 확인), E-7 동시구독 한도·E-8 rate limit 수치 실측(보수적 5/s 로 운용 중). 나머지 전부 완료.

---

## A. 키움증권 — 모의투자 API 발급 ⛔ 최우선 (심사·발급 시간 소요)
> 목표: **모의용** App Key/Secret + 모의계좌 번호 확보. 자동매매의 필수 선행조건.

- [x] A-1. 키움증권 계좌 개설 ✅
- [x] A-2. `openapi.kiwoom.com` REST API 사용 신청 ✅
- [x] A-3. **상시모의투자** 참가신청 → 모의계좌 생성 ✅
- [x] A-4. **모의용** App Key / App Secret 발급 ✅ (사용자 보관, 채팅 미공유)
- [x] A-5. 모의계좌 번호 확인 (`KIWOOM_ACCOUNT_NO`) ✅
- [ ] A-6. 이용약관 확인 — 자동매매 허용 범위 · 호출한도(rate limit)

**산출물(시크릿):** `KIWOOM_APP_KEY`, `KIWOOM_SECRET`(모의), `KIWOOM_ACCOUNT_NO`
> ⚠️ 값은 채팅에 붙여넣지 말 것. 나중에 `engine/.env`(깃 제외)에 직접 입력. 실전 키는 Phase 7 전까지 금지.

## B. Supabase — 중계·DB (무료 티어)
- [x] B-1. `supabase.com` 가입 ✅ (2026-09-02)
- [x] B-2. 새 프로젝트 생성 ✅ (ref `ftfamqtxiaygbmnfuowt`)
- [x] B-3. 키 확보 ✅ — **신규 키 체계**: `SUPABASE_URL`, publishable key(앱, `sb_publishable_…`), secret key(봇, `sb_secret_…`), auth 사용자 UID(`SUPABASE_OWNER_UUID`)
- [x] B-4. 마이그레이션 0001~0005 적용 ✅ (0001~0004 SQL Editor 수동, 0005 부터 CLI `db push`)

**산출물(시크릿):** `SUPABASE_URL`, publishable key(앱 `env.dart`), `SUPABASE_SECRET_KEY`, `SUPABASE_OWNER_UUID`

## C. 로컬 런타임 설치
> 2026-08-31 점검 결과 반영. Git만 설치돼 있음.

- [x] C-1. **Python 3.12.10** ✅ 설치 완료 (winget, 사용자 범위 `...\Programs\Python\Python312`, pip 25.0.1, PATH 등록·스텁보다 우선). 새 터미널에서 `python` 사용 가능.
- [x] C-2. Git ✅ (2.55.0 설치됨)
- [x] C-3. Supabase CLI ✅ v2.116.0 단일 실행파일(`D:\dev\supabase`, PATH). Node 불필요. login/link 완료(2026-09-03)
- [~] C-4. Flutter SDK ✅ **이미 설치됨** (`D:\dev\flutter`, v3.47.2 stable / Dart 3.13.2). **PATH 미등록**만 남음(Phase 5 전 등록 or 전체경로 호출). Android Studio는 Phase 5에서 확인.
- [~] C-5. Docker — **보류**(D-015: 클라우드 이관은 venv+systemd). Android Studio/SDK 는 2026-09-03 설치(APK 빌드)

## D. 프로젝트 초기화 (제가 진행 가능 — 키 불필요)
- [x] D-1. `git init -b main` + 첫 커밋 ✅ (2026-09-01, 커밋 e3913f8)
- [x] D-2. `engine/` Phase 0 스캐폴딩 ✅ (`requirements.txt`, `.env.example`, `tools/check_kiwoom_token.py`, `README.md`). src/ 전체 구조는 Phase 1에서.

## E. 키움 실제 스펙 실측 🔴 (Phase 2 블로커)
> A 완료 후. 공식 SDK/문서로 실제 값 확인해 [`docs/01-broker-kiwoom.md`](docs/01-broker-kiwoom.md) "확정 스펙" 표를 채운다.

- [x] E-2. 모의/실전 REST·WebSocket Base URL 확인 ✅ (mockapi.kiwoom.com / api.kiwoom.com, WS :10000)
- [x] E-3. 토큰 발급 endpoint·필드 확인 ✅ (`POST /oauth2/token`, body grant_type/appkey/secretkey, 만료시간은 실행 시 실측)
- [x] E-5. 잔고조회 TR 확인 ✅ (kt00018 `/api/dostk/acnt`)
- [x] E-6. 현재가 ka10001 `/api/dostk/stkinfo` · 호가 ka10004 ✅ (Phase 2)
- [x] E-4. 주문 kt10000(매수)/kt10001(매도)/kt10003(취소) `/api/dostk/ordr` ✅ 왕복주문 실증(2026-09-03). 정정 kt10002 는 미검증
- [~] E-7. WebSocket 구독 형식 ✅ 실측(LOGIN→REG 0B→REAL, PING echo) / **동시구독 한도 미실측**
- [ ] E-8. Rate limit 수치 — 미실측(보수적 토큰버킷 5/s 운용)
- [x] E-9. docs/01 스펙 표 — 토큰·잔고·주문·현재가·WS 채움 ✅ (한도 2칸만 ⬜)

---

## Phase 0 완료 게이트
- [x] 키움 모의 App Key/Secret로 **접근토큰 발급 성공** ✅ (2026-09-01, 스모크 테스트)
- [x] 키움 모의계좌 **잔고조회** ✅ (Phase 2, 예탁 5천만)
- [x] Supabase 프로젝트 접속 + CLI 로컬 링크 ✅ (2026-09-03)
- [x] `python` 3.12 ✅ / `supabase` CLI ✅
- [~] docs/01 스펙 표 — 한도 2칸 제외 완료

> **결론:** Phase 1(분석 로직 이식)에 필요한 게이트는 모두 통과. Supabase(B)는 Phase 3 전까지 병행하면 됨.

## 여기서 안 하는 것 (명시)
- ❌ Firebase/FCM (백그라운드 푸시) — Phase 5-B에서 결정
- ❌ 키움 실전(real) 키 — Phase 7 게이트 통과 전 금지
- ❌ Flutter/Docker 지금 설치 — 해당 Phase에서

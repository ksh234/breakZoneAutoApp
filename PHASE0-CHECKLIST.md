# Phase 0 체크리스트 — 환경 구축 & API 스펙 확정

> [`ROADMAP.md`](ROADMAP.md) Phase 0의 **실행용 체크리스트**. 항목을 완료하면 `[ ]` → `[x]` 로 바꾸며 순차 진행한다.
> 원칙: **모의(demo)부터**. 실전 키·Firebase는 여기서 다루지 않는다(Phase 5-B / Phase 7).

## 진행 상황 요약
- 착수일: 2026-08-31
- 현재 단계: **A(키움 신청) 대기 + C(런타임 설치) 진행 중**
- 병렬: 키움 발급을 기다리는 동안 Phase 1(분석 로직 이식)은 키 없이 착수 가능.

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
- [ ] B-1. `supabase.com` 가입 (GitHub 계정 가능)
- [ ] B-2. 새 프로젝트 생성 — 리전 **Northeast Asia (Seoul)** 권장, DB 비밀번호 설정
- [ ] B-3. API 설정에서 3개 값 확보:
  - [ ] `SUPABASE_URL`
  - [ ] `anon` public key (앱용, 공개 가능)
  - [ ] `service_role` key (봇 전용 — **앱·깃에 절대 미포함**)

**산출물(시크릿):** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

## C. 로컬 런타임 설치
> 2026-08-31 점검 결과 반영. Git만 설치돼 있음.

- [x] C-1. **Python 3.12.10** ✅ 설치 완료 (winget, 사용자 범위 `...\Programs\Python\Python312`, pip 25.0.1, PATH 등록·스텁보다 우선). 새 터미널에서 `python` 사용 가능.
- [x] C-2. Git ✅ (2.55.0 설치됨)
- [ ] C-3. Node.js LTS + Supabase CLI ❌ — Phase 3에서 필요
- [~] C-4. Flutter SDK ✅ **이미 설치됨** (`D:\dev\flutter`, v3.47.2 stable / Dart 3.13.2). **PATH 미등록**만 남음(Phase 5 전 등록 or 전체경로 호출). Android Studio는 Phase 5에서 확인.
- [ ] C-5. (선택) Docker ❌ — Phase 8에서 필요

## D. 프로젝트 초기화 (제가 진행 가능 — 키 불필요)
- [x] D-1. `git init -b main` + 첫 커밋 ✅ (2026-09-01, 커밋 e3913f8)
- [x] D-2. `engine/` Phase 0 스캐폴딩 ✅ (`requirements.txt`, `.env.example`, `tools/check_kiwoom_token.py`, `README.md`). src/ 전체 구조는 Phase 1에서.

## E. 키움 실제 스펙 실측 🔴 (Phase 2 블로커)
> A 완료 후. 공식 SDK/문서로 실제 값 확인해 [`docs/01-broker-kiwoom.md`](docs/01-broker-kiwoom.md) "확정 스펙" 표를 채운다.

- [x] E-2. 모의/실전 REST·WebSocket Base URL 확인 ✅ (mockapi.kiwoom.com / api.kiwoom.com, WS :10000)
- [x] E-3. 토큰 발급 endpoint·필드 확인 ✅ (`POST /oauth2/token`, body grant_type/appkey/secretkey, 만료시간은 실행 시 실측)
- [x] E-5. 잔고조회 TR 확인 ✅ (kt00018 `/api/dostk/acnt`)
- [~] E-6. 현재가/호가 TR 부분 확인 (호가 ka10004 `/api/dostk/mrkcond`; 현재가 TR은 Phase 2)
- [ ] E-4. 주문(매수/매도/정정/취소) TR·스키마 — **Phase 2에서 실측**
- [ ] E-7. 실시간 WebSocket 구독 형식·동시구독 한도 — Phase 2
- [ ] E-8. Rate limit 수치 — Phase 2
- [~] E-9. docs/01 스펙 표: 토큰·잔고·base URL 칸 채움 ✅ / 주문·실시간은 Phase 2 (표에 ⬜ 표기)

---

## Phase 0 완료 게이트 (전부 통과해야 Phase 1→2 진행)
- [ ] 키움 모의 App Key/Secret로 **접근토큰 발급 1회 성공** (curl/Postman)
- [ ] 키움 모의계좌 **잔고조회 200 응답**
- [ ] Supabase 프로젝트 접속 + CLI 로컬 링크
- [ ] `python --version` 3.11+, `supabase --version` 동작
- [ ] docs/01 "확정 스펙" 표의 모든 칸이 실제 값으로 채워짐

## 여기서 안 하는 것 (명시)
- ❌ Firebase/FCM (백그라운드 푸시) — Phase 5-B에서 결정
- ❌ 키움 실전(real) 키 — Phase 7 게이트 통과 전 금지
- ❌ Flutter/Docker 지금 설치 — 해당 Phase에서

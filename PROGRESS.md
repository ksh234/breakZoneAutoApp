# 진행 상황 (PROGRESS) — breakZoneAutoApp

> **새 세션은 이 파일을 가장 먼저 읽는다.** "지금 어디까지 왔고, 다음에 무엇을 하는가"의 단일 출처(SSOT).
> 이 프로젝트는 **로드맵 Phase 단위로 세션을 나눠** 진행한다. 매 세션 끝에 이 파일의 §다음 할 일 · §세션 로그를 갱신한다.
>
> **읽는 순서(신규 세션):** ① 이 파일(PROGRESS) → ② [ROADMAP.md](ROADMAP.md) → ③ 현재 Phase가 가리키는 [docs/](docs/) → ④ [DECISIONS.md](DECISIONS.md)(왜 그렇게 정했나) → ⑤ [PHASE0-CHECKLIST.md](PHASE0-CHECKLIST.md)(환경/계정 진행 상태)

---

## 🧭 한눈에 (현재 상태)

| 항목 | 값 |
|---|---|
| **마지막 업데이트** | 2026-09-01 |
| **현재 Phase** | **Phase 0** (환경 구축 & API 스펙 확정) — 진행 중 |
| **코드 상태** | 아직 없음. 설계 문서 + 환경/계정 준비 단계 |
| **다음 마일스톤** | 키움 모의 API 키 발급 → docs/01 스펙 실측 → Phase 1(분석 로직 이식) 착수 |
| **블로커** | 키움 모의 App Key/Secret 발급(사용자 진행 중) |

---

## ▶️ 다음에 할 일 (바로 착수 지점)

**사용자(🙋) 담당 — 외부 절차:**
1. `openapi.kiwoom.com` → REST API 사용 신청 → **모의투자 등록** → **모의 App Key/Secret 발급** → 모의계좌 번호 확인
2. (병행) [supabase.com](https://supabase.com) 프로젝트 생성(Seoul 리전) → URL·anon·service_role 키 확보

**Claude(🤖) 담당 — 키 없이 착수 가능(대기 중, 사용자 "시작" 신호 시):**
1. `git init` + 첫 커밋 (D-1)
2. `engine/` 스캐폴딩 (D-2 / Phase 1-1)
3. breakZone 분석 로직 이식 → 후보 산출 함수 (Phase 1)

**키 발급 후(🤝):** 키움 공식 저장소로 docs/01 스펙 표 실측 → Phase 2(브로커 연동).

---

## ✅ 완료한 일 (요약)

- [x] 설계 문서 7종(docs/00~06) + ROADMAP 통독·분석
- [x] Phase 0 체크리스트 작성([PHASE0-CHECKLIST.md](PHASE0-CHECKLIST.md))
- [x] 문서 관리 체계 수립(PROGRESS/DECISIONS)
- [x] **Python 3.12.10 설치**(winget, 사용자 범위, PATH 등록)
- [x] Flutter 기존 설치 확인(`D:\dev\flutter` v3.47.2 — 재설치 불필요)
- [x] 키움 "REST API MCP" 정체 조사(공식 저장소에 MCP 추가됨 — 아래 결정 참조)
- [x] 키움 계좌 개설(사용자)

---

## 🗂 세션 로그 (최신 → 과거)

### 세션 2026-09-01
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

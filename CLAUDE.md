# CLAUDE.md — breakZoneAutoApp

> 이 파일은 세션 시작 시 자동 로드된다.
> **① 새 세션은 먼저 [`PROGRESS.md`](PROGRESS.md) 를 읽어 "지금 어디까지 왔고 다음에 뭘 하는지" 파악한다.** (세션 간 인수인계용 단일 진입 문서 — 결정 근거는 [`DECISIONS.md`](DECISIONS.md))
> ② 그다음 [`ROADMAP.md`](ROADMAP.md) 와 [`docs/00-architecture.md`](docs/00-architecture.md) 로 전체 그림을 확인하고, 현재 Phase 작업을 이어간다.
> **③ 매 세션 끝에 PROGRESS.md(§세션 종료 시 갱신 규칙)와 관련 체크리스트를 갱신한다.** 우리가 결정·진행한 모든 내용은 md에 상세히 기록한다.

## 이 프로젝트가 뭔가
KRX 투자경고종목(경고주)을 분석해 **자동매매**하는 시스템. 기존 `breakZone`(분석 대시보드)의 로직을 재사용한다.

```
[전략엔진(Python 봇) 집PC→클라우드] ─▶ [키움 REST API] (모의/실전 주문)
        │ outbound-only (상태 push / 명령 구독)
        ▼
[Supabase 중계·DB·Realtime] ◀── [Flutter 앱 모니터링·원격제어]
```

## 폴더 배치 (중요)
`breakZone/` 와 `breakZoneAutoApp/` 는 **같은 부모 폴더 아래 형제(sibling)** 로 둔다. 문서의 `../breakZone` 참조와 코드 이식이 이 배치를 전제로 한다. `breakZone` 은 참조용으로 **수정하지 않는다**(분석 로직은 `engine/src/analysis/` 로 복사·이식).

## 확정된 핵심 결정 (바꾸면 ROADMAP §1 표부터 갱신)
- 증권사: **키움 REST API** (모의투자부터). 미래에셋은 개인 자동매매 API 미제공.
- 앱 **Flutter** · 중계 **Supabase(단독, 다른 백엔드 없음)** · 봇 **Python 3.11+**.
- 백그라운드 푸시(FCM/Firebase)는 **1단계 제외**. 앱 알림은 Supabase Realtime(인앱)로. FCM 추가 여부는 **Phase 5-B에서 결정**.
- 봇은 **outbound 연결만** → NAT/유동IP 무관, 클라우드 이관 = 프로세스 이동.
- 처음엔 집 Windows PC에서 간헐 구동.

## 절대 원칙 (안전)
1. **모의투자(demo)로 충분히 검증하기 전 실계좌(real) 금지** — ROADMAP Phase 6·7 게이트.
2. 모든 자동 주문에 **리스크 가드**(1회 한도·보유수·일손실·가격 sanity·중복주문). `docs/05`.
3. **kill-switch**(전량청산+정지)는 앱·서버 양쪽에서 동작.
4. **시크릿(키움 키, service_role)은 코드/깃에 넣지 않는다.** `.env`/OS 키체인. 앱엔 anon key만.
5. 같은 키움 계좌 **이중 실행 금지**(락).
6. 전략 임계값은 감이 아니라 **백테스트로** 결정. `docs/03`.

## 키움 스펙 주의
ROADMAP/docs의 도메인·TR코드·호출한도 값은 **자리표시자**다. 코딩 전 `openapi.kiwoom.com` 공식 문서와 공식 SDK(`github.com/Kiwoom-Securities/Kiwoom-REST-API`)로 **실측해 `docs/01`의 스펙 표를 채운다.**

## 현재 상태 (2026-09-03)
**Phase 0~5 구현 완료** (봇: analysis/broker/relay/strategy + 테스트 158개, 앱: Flutter 7화면 + 폰 APK). 키움 왕복주문·봇↔Supabase↔앱 제어 라이브 실증 완료. **Phase 8 클라우드 이관을 앞당겨 진행 중**(D-015): 락·영속화·드라이런·GitHub 원격 완료, VM 생성은 사용자 보류. 다음 할 일은 **PROGRESS.md §다음에 할 일**이 SSOT.

## 작업 환경 메모 (Claude용)
- **문서/코드 다중 편집은 scratchpad 에 python 스크립트로 작성 후 실행**한다. Bash 툴 히어독은 백슬래시·따옴표가 깨지는 사례 있음(2026-09-03). 단일 치환은 Edit 툴.
- **`git push` 는 단독 명령으로 실행**(commit 과 한 줄에 묶으면 자동모드 분류기가 차단). 커밋 메시지는 `-F <파일>`.
- Supabase 스키마 변경 = `supabase/migrations/NNNN_*.sql` 작성 → `D:\dev\supabase\supabase.exe db push` (CLI link 완료, DB 비밀번호 불필요).
- 봇 실행/검증: `engine/run_bot.bat`(바탕화면 `breakZone 봇 시작.bat`). 테스트 `engine/.venv/Scripts/python.exe -m pytest -q`. Flutter는 `D:\dev\flutter\bin\flutter.bat` 전체경로.
- 요청 범위 밖 코드 변경은 먼저 물어본다(사용자 피드백 2026-09-03).

## 환경
- OS: Windows. 셸은 PowerShell(주) / Bash 병행. 경로는 절대경로 선호.
- 문서·주석·커밋 메시지는 한국어.

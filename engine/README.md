# engine — 전략 엔진(봇)

KRX 경고주 분석 + 키움 REST 자동매매 봇. 설계: [../ROADMAP.md](../ROADMAP.md), [../docs/](../docs/). 사용법: [../사용법.md](../사용법.md).

## 구조 (2026-09-03)
```
src/
├── main.py            엔트리: 로깅 → 브로커/릴레이 → LockKeeper(이중 실행 락) → tick 루프
├── config.py          .env 로드 (KIWOOM_*, SUPABASE_*, BOT_*, LOG_*)
├── analysis/          breakZone 이식 (KIND 크롤·pykrx·네이버) + candidates.py 후보 산출
├── broker/            BrokerAdapter + KiwoomRestBroker (REST 동기 + WS 스레드)
├── relay/             Relay(Supabase 쓰기/읽기/명령 폴링/락/전략상태) + DryRunRelay(쓰기 무시)
└── strategy/          params · indicators(envelope) · rules(진입/청산 순수함수) · risk · state · engine(오케스트레이션) · market
tests/                 pytest 158개 (외부 I/O 전부 mock)
tools/                 check_kiwoom_token.py(토큰·잔고) · check_supabase.py(중계) · it_kiwoom.py(왕복주문 통합)
run_bot.bat            집 PC 실행 런처 (바탕화면 "breakZone 봇 시작.bat" 이 호출)
logs/bot.log           회전 파일 로그 (gitignore)
```

## 실행
```powershell
cd engine
.\.venv\Scripts\python.exe -m pytest -q          # 테스트
.\.venv\Scripts\python.exe -m src.main           # 봇 (또는 run_bot.bat)
.\.venv\Scripts\python.exe tools/check_kiwoom_token.py
.\.venv\Scripts\python.exe tools/check_supabase.py
```
venv 활성화(`Activate.ps1`)는 실행정책 문제로 생략하고 `.venv\Scripts\python.exe` 를 직접 호출한다.

## .env (깃 제외 — `.env.example` 참고)
| 키 | 설명 |
|---|---|
| `KIWOOM_MODE` `KIWOOM_APP_KEY` `KIWOOM_SECRET` `KIWOOM_ACCOUNT_NO` | 키움 (demo 고정) |
| `SUPABASE_URL` `SUPABASE_SECRET_KEY` `SUPABASE_OWNER_UUID` | Supabase 봇 전용 secret key(`sb_secret_…`) + 앱 사용자 UID |
| `BOT_DRY_RUN` | 1=주문·Supabase 쓰기 금지, `[DRY]` 판정 로그만. 클라우드 이관 후 PC 는 1 권장 |
| `BOT_HOLDER_ID` `BOT_LOCK_STALE_SEC` `BOT_LOCK_RENEW_SEC` | 이중 실행 락(기본 호스트명 / 90 / 15) |
| `LOG_LEVEL` `LOG_DIR` | 로그. `LOG_DIR=0` 이면 파일 로그 끔(서버 journald) |

## 동작 요약
- 시작 시 `status=stopped`. 앱 제어의 **시작** 명령으로 running. settings 는 시작·`set_param`·30초 주기로 재로드.
- 락 획득 인스턴스만 LIVE(주문·DB 쓰기·명령 처리). 미획득/드라이런은 관찰 모드.
- 전략상태(분할매수·고점·저점)는 `strategy_state` 에 저장, 재시작 시 복원.
- Ctrl+C 안전 종료(락 해제).

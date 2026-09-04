# 진행 상황 (PROGRESS) — breakZoneAutoApp

> **새 세션은 이 파일을 가장 먼저 읽는다.** "지금 어디까지 왔고, 다음에 무엇을 하는가"의 단일 출처(SSOT).
> 이 프로젝트는 **로드맵 Phase 단위로 세션을 나눠** 진행한다. 매 세션 끝에 이 파일의 §다음 할 일 · §세션 로그를 갱신한다.
>
> **읽는 순서(신규 세션):** ① 이 파일(PROGRESS) → ② [ROADMAP.md](ROADMAP.md) → ③ 현재 Phase가 가리키는 [docs/](docs/) → ④ [DECISIONS.md](DECISIONS.md)(왜 그렇게 정했나) → ⑤ [PHASE0-CHECKLIST.md](PHASE0-CHECKLIST.md)(환경/계정 진행 상태)

---

## 🧭 한눈에 (현재 상태)

| 항목 | 값 |
|---|---|
| **마지막 업데이트** | 2026-09-04 |
| **현재 Phase** | **Phase 0~5 완료 + 폰 앱 배포 + 라이브 실증(왕복주문·제어).** 전략 정교화 완료 |
| **코드 상태** | engine analysis/broker/relay/strategy + 테스트 **172개**. Flutter 앱 7화면 + **안드로이드 APK 폰 설치·로그인 정상**(설정반영 수정본 재설치 필요). 사용법 문서([사용법.md](사용법.md)). |
| **다음 마일스톤** | ① 집 PC 에서 **단계 B 첫 모의매매 관찰**(장중, 새 코드) ② **클라우드 VM 생성(사용자 보류 중)** → 서버 설치·전환 → Phase 6 장기 검증 |
| **블로커** | VM 생성 보류(사용자 "나중에"). Oracle 무료티어는 가입 시 한국 리전 미제공 상태였음(2026-09-03). 대안: 며칠 뒤 Oracle 재시도 / AWS Lightsail 서울(월 $5) / Azure 무료 12개월. |

---

## ▶️ 다음에 할 일 (바로 착수 지점)

**🙋 단계 B 본편 — 첫 모의매매 관찰 (평일 장중 09:00~15:30, 집 PC = LIVE 봇)**
0. **폰에 새 APK 재설치**(설정 저장 → set_param 명령 전송 수정본. `app/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk`, 2026-09-03 16:11 빌드)
1. 봇 실행: 바탕화면 **`breakZone 봇 시작.bat`** 더블클릭(= `engine/run_bot.bat`). 로그에 **"락 획득(ksh)"** 확인. 로그 파일 `engine/logs/bot.log`. PC `.env` 는 `BOT_DRY_RUN` 없음/0 유지(PC 가 아직 운용 봇).
2. 앱(폰/PC): 제어 → **시작** → 설정 → **자동매매 활성화 ON** → 저장 → 이벤트 탭에 **"설정 반영 enabled=True"** 뜨는지 확인(이게 안 뜨면 설정 미반영 버그 재발).
3. 관찰: 후보 탭에 **상태 "정상" + 하락 30%↑** 종목이 매수 후보. 조건 맞으면 주문/포지션에 뜸. 매수 시 `strategy_state` 에 행 생성됨(Supabase 대시보드로 확인 가능).
3-b. 장 마감 후 로그 점검: `engine/logs/bot.log` 에서 `disconnected`·`재시도` 검색 → 0건이면 통신 안정화(2026-09-04) 확인 완료. 종료 후 앱 상태가 **stopped** 로 바뀌는지 확인.
4. 이상 시 제어 → **긴급정지(kill)**.
> 조건이 까다로워 당장 매매 없을 수 있음(정상). 핵심은 봇이 안 죽고 조건 맞으면 주문 나가는지.
> ⚠️ 저가 반등 2% + 기준 30% 조합은 실효 기준 ≈31.4%(§열려있는 질문). 관찰 중 매수가 안 나오면 이 영향일 수 있음.

**☁️ 클라우드 이관 재개 시(사용자 VM 준비 후):** docs/06 부록 A 로 VM 생성 → IP·사용자명·키파일명 전달 → Claude: `ssh` 접속 확인 → `sudo bash infra/server/setup.sh https://github.com/ksh234/breakZoneAutoApp.git` → `.env` 배치(`BOT_HOLDER_ID=cloud-seoul`) → 스모크(`tools/check_kiwoom_token.py`, `tools/check_supabase.py`, KIND 크롤링) → PC 봇 종료 → `systemctl start breakzone-bot` → 앱 "봇 LIVE" 확인 → PC `.env` `BOT_DRY_RUN=1`.

**그다음 — Phase 6 (백테스트 + 모의 2~4주 검증):** 파라미터 데이터로 튜닝 → 실계좌(Phase 7) 전 신뢰 확보.

**🚀 클라우드 이관 진행표 (D-015):** 1단계 봇 준비 ✅ → 2단계 GitHub 원격 ✅(`github.com/ksh234/breakZoneAutoApp` private, origin/main 추적, 비대화 push OK) → 3단계 VM 생성·SSH(사용자) ⬜ → 4단계 서버 설치·systemd(Claude, `infra/server/setup.sh`) ⬜ → 5단계 전환 검증(PC `.env` `BOT_DRY_RUN=1`, 클라우드 LIVE) ⬜

**미결/후속(급하지 않음):**
- 키움 정정 TR(kt10002) 미검증(취소+재주문 대체 가능).
- 오프라인 버퍼(네트워크 끊김 재전송) 후속.
- 봇 24시간화 = Phase 8 클라우드 이관.

**재현/실행:**
```powershell
# 봇
cd D:\myWorkspace\breakZoneAutoApp\engine
.\.venv\Scripts\python.exe -m pytest -q                     # 테스트 172개
.\.venv\Scripts\python.exe -m src.main                      # 봇 실행(장중)
# 앱
cd D:\myWorkspace\breakZoneAutoApp\app
& "D:\dev\flutter\bin\flutter.bat" run -d chrome            # PC 웹
& "D:\dev\flutter\bin\flutter.bat" build apk --release --split-per-abi   # 폰 APK(arm64=요즘폰)
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
- [x] **Phase 2: 키움 Broker Adapter + 왕복주문 실증(매수→미체결→취소)** ✅
- [x] **Phase 3: Supabase 마이그레이션(7테이블+RLS+Realtime) + Relay 중계 + 라이브 검증** ✅
- [x] **Phase 4: 전략 엔진(규칙·리스크·엔진·main) + 사용자 전략 확정·정교화 + 단계 A 제어 실증** ✅
- [x] **Phase 5: Flutter 앱 7화면 + 안드로이드 APK 폰 설치·로그인 정상** ✅
- [x] 사용법 문서([사용법.md](사용법.md)). 설정 미반영 버그 수정(봇 30초 재로드 + 앱 set_param 전송) + APK 재빌드
- [x] **Supabase CLI** 설치·link·마이그레이션 이력 repair → 이후 스키마 변경은 `db push`
- [x] **Phase 8 클라우드 이관 1·2단계:** 이중 실행 락 `bot_lock` · 전략상태 영속화 `strategy_state` · 드라이런 `BOT_DRY_RUN` · GitHub private 원격 · `infra/server/` 설치 자산 · 집 PC 런처 bat + 파일 로그
- [x] 테스트 **158개** 통과. 문서-실제 정합성 점검(2026-09-03 저녁)

---

## 🗂 세션 로그 (최신 → 과거)

### 세션 2026-09-04 오전 (첫 장중 실행 로그 분석 → Supabase 통신 안정화)
- **첫 장중 실행(집 PC, bat):** 08:55 시작 → 08:56 앱 "시작" 수신 → 10:27 Ctrl+C 종료. 후보 19종목 10분 주기 갱신 정상. **매수·매도 0건**(진입 조건 충족 종목 없음, 차단·tick 오류 없음). 사용자 "봇이 이상한 것 같다" → 로그 분석.
- **이상 1 — Supabase 쓰기 간헐 실패(실제 버그):** 09:01~10:27 `httpx.RemoteProtocolError: Server disconnected` — 명령 폴링 경고 52회, `strategy_state` 저장 실패 19회, 하트비트·후보갱신 실패 각 1회, 종료 시 `cannot receive data before headers` 1회. 원인: supabase-py(2.31) postgrest 세션이 **HTTP/2 + 두 스레드(메인 tick·명령 폴링) 공유**, 유휴 연결 서버 종료/동시 사용 시 오류. 라이브러리 재시도는 GET 503/520 만 → 쓰기는 즉시 실패. 피해: 명령은 다음 폴링에 재수신(유실 없음), 저점 저장 실패로 `strategy_state` 비어 복원 신뢰 불가. 주문 기록 쓰기가 걸렸다면 앱에 안 보이는 주문 가능성 → 장기 운용 전 필수 수정.
- **이상 2 — 종료 후 앱에 running 잔존:** 종료 시 status 를 안 바꿔 bot_state=running + 하트비트 정지 상태로 표시(사용자가 느낀 "이상"의 직접 원인 추정).
- **수정(사용자 승인, 커밋 참조):** ① `Relay._harden_http()` — 생성 직후 postgrest 세션을 같은 base_url·헤더의 **HTTP/1.1 httpx.Client**(timeout 15/5s, keepalive 15s, 연결 4)로 교체 ② `Relay._exec()` — 모든 요청을 `threading.Lock` 으로 직렬화 + `httpx.TransportError` 시 세션 재생성 후 **1회 재시도**(비전송 오류는 재시도 안 함) ③ `main.shutdown()` — status=stopped 하트비트 push → "봇 종료" 이벤트 → 락 해제.
- **검증:** 라이브 스모크(세션 교체·헤더 유지·쓰기·락·20초 유휴 후 재사용 OK, bot_state=stopped 반영) + **60초 2스레드 스트레스**(폴링 1.5초 + 하트비트/상태저장 5~22초 유휴 포함: 폴링 39·하트비트 8·저장 8·락 2 전부 성공, 재시도 0). 테스트 +8 → **166개**.
- 재시도 시 쓰기 중복 가능성(주문/이벤트 행 중복)은 "유실보다 낫다"로 수용. 관찰 항목으로 기록.
- 다음: 다음 장중 실행에서 `Server disconnected` 경고가 사라졌는지 로그 확인(`Select-String bot.log -Pattern 'disconnected|재시도'`).
- **질문 2건(설명만):** ① `min_price`=1,000 → 현재가 1,000원 **미만** 매수 안 함(1,000원은 허용), 신규·추가매수 공통, 0=무제한. ② 분할익절 후 재상승 시 → 분할익절은 1회, 이후 잔량은 트레일링/상한가만(+15% 재검사 없음).
- **전략 추가(사용자 요청, D-013 보강) — X2b 2차 상승 전량매도:** `post_sell_gain_pct`(%) 신규. 분할매도 후 **1차 매도가 대비** 이 % 이상 → 잔량 전량. 기본 0=끔 → **앱 설정 "2차 상승 전량매도(%)" 에 수치 입력 필요**. 우선순위 상한가 → 2차 상승 → 트레일링. `PositionState.partial_sell_price` + 마이그레이션 **0006**(strategy_state 컬럼) CLI 적용. 앱 설정 항목 16개 → APK 재빌드(**폰 재설치 필요**). 테스트 +6. docs/03 §2.2·§2.2b·§6, 사용법 §5·§8, DECISIONS 갱신.

### 세션 2026-09-03 저녁 (상태 분석 → 설정버그 수정 → Supabase CLI → 클라우드 이관 1·2단계 → 문서 정합성)
커밋 범위 `61e162d`…(이 항목 커밋) / 원격 `github.com/ksh234/breakZoneAutoApp` main 동기화. 테스트 137 → **158개**.

**A. 상태 분석·문서 정리**
- 세션 시작 실측: 테스트 137 통과, `.env`/`env.dart` 존재, git clean. 문서-코드 일치.
- PROGRESS 하단 3구역(결정 요약·환경 현황·열린 질문) 현행화(D-007/D-008 확정 반영, 완료 항목 제거).
- **사용자 질문(저가 반등 × 진입기준):** 기준 30%·반등 2% 설정에서 반등으로 30% 안쪽이 되면? → `should_enter` 가 현재가 drop_ratio ≥ 기준을 먼저 검사 → **매수 안 됨**, `_update_candidate_lows` 가 저점도 리셋. 실효 기준 ≈ 31.4%. 30~31.4% 구간에서 오르내리는 종목은 계속 놓침. 규칙 변경("저점이 구간 안이면 반등 후 이탈해도 매수") 여부는 사용자 판단 대기 → §열려있는 질문.

**B. 설정 미반영 버그 수정 (앱→봇)**
- 발견: 앱 설정 저장이 `settings` update 만 하고 `set_param` 명령을 안 보냄 + 봇은 시작/`set_param` 때만 로드 → 실행 중 봇에 "자동매매 ON" 미반영(단계 B 절차 자체가 실패할 상황).
- 수정 ① 봇: `PARAMS_RELOAD_SEC=30` 주기 재로드(정지/장외 포함), 값 변경 시만 "설정 반영 <diff>" 이벤트, `set_param` 은 변경 여부 반환. ② 앱: 저장 직후 `sendCommand('set_param')`.
- 테스트 +5(142). `flutter analyze` 0, APK 재빌드(arm64 17.9MB) 전달 → **폰 재설치 필요(미완)**.

**C. Supabase CLI 도입**
- v2.116.0 단일 실행파일 `D:\dev\supabase`(winget/scoop 없음 → GitHub 릴리스), 사용자 PATH, `supabase init`(config.toml 커밋).
- 사용자 `supabase login`(브라우저 승인) + `supabase link --project-ref ftfamqtxiaygbmnfuowt`. **DB 비밀번호 불필요**(신 CLI 는 액세스 토큰으로 login role 생성).
- Claude: `migration repair --status applied 0001 0002 0003 0004` → `migration list` 로컬=원격 → `db push --dry-run` up to date. 이후 마이그레이션은 `db push` 로 직접 적용.

**D. 결정 (사용자 확정)**
- 질문 "계정 늘리면 다른 사람도 별도 계좌로 자동매매?" → 현재 settings/bot_state id=1 단일행 + 봇 1프로세스=계좌 1개라 불가. 확장안(owner 키 스키마 + 사람별 봇) 제시. **D-014 단일 사용자 유지.**
- 질문 "장기 테스트 전에 클라우드로 옮기는 게 어떤가 / 옮긴 뒤 수정하면 계속 옮겨야 하나" → 찬성. 재배포 = `git pull`+재시작 한 줄(Claude 가 SSH). **D-015 Phase 8 앞당김**(Docker 생략, 국내 VM, venv+systemd). 선행 필수: 락·영속화·GitHub.
- 질문 "락 우선순위·PC 테스트 방법" → 락은 선착순 유지(우선순위 없음), PC 는 `BOT_DRY_RUN=1` 드라이런으로 판정만 관찰. 주문 경로 실증 필요 시 클라우드 서비스 잠시 정지.
- 질문 "VM/Supabase 는 웹서버/DB 서버?" → Supabase=백엔드 전부(DB+인증+실시간), VM 봇=요청 안 받는 워커, 키움=외부 결제사 API 격. 설명만(문서 변경 없음).

**E. 클라우드 이관 1단계 — 봇 준비 (커밋 faf6bfd)**
- 마이그레이션 **0005** `bot_lock`(id=1, holder_id, heartbeat_at) + `acquire_bot_lock(owner,holder,stale_sec)`(INSERT…ON CONFLICT DO UPDATE…WHERE 원자적, 획득=갱신, stale 승계) / `release_bot_lock`. security definer + anon/authenticated 실행 권한 revoke. `strategy_state`(owner,code: entries_done·invested_krw·partial_sold·peak_since_partial·zone_low). 둘 다 RLS select 본인. `db push` 로 원격 적용, **원격 락 스모크**(A획득→B실패→A갱신→stale0 B승계→A실패→해제→A재획득) 실측 OK.
- relay: `acquire_lock/release_lock`(rpc), `load/save/delete_strategy_state`. **`DryRunRelay`**(읽기 위임·쓰기 무시).
- engine: `set_live(bool)`(relay 교체), `restore_state()`, `_persist_state(code)`(매수·분할매도·고점 변경·저점 변경 시 저장, 청산/리셋 시 삭제), `_dry_log`(종목·사유당 하루 1회 `[DRY]`), kill/close_position 드라이런 차단.
- main: **`LockKeeper`**(start: 획득→`go_live`(싱글턴·복원·리스너·"봇 LIVE" 이벤트) / 실패→관찰; tick: 15초마다 갱신·재시도, 승계 시 LIVE, 갱신 실패 시 "락 상실" critical + 관찰; release). `BOT_DRY_RUN=1` 이면 락 무관 관찰 + status=running. config: `BOT_HOLDER_ID`(호스트명), `BOT_LOCK_STALE_SEC=90`, `BOT_LOCK_RENEW_SEC=15`.
- 테스트 +16(158): 락 rpc·strategy_state·DryRunRelay·드라이런 엔진·영속화/복원·LockKeeper. docs/02·03·05·06·사용법 갱신.

**F. 클라우드 이관 2단계 — GitHub 원격 (커밋 de83601~)**
- `infra/server/setup.sh`(Ubuntu 22.04/24.04: python3.12·bot 사용자·/opt clone·venv·systemd 등록) · `breakzone-bot.service`(Restart=always, SIGINT 안전종료, KST, LOG_DIR=0→journald) · `deploy.sh`(pull→deps 변경 시 설치→pytest -x→restart). `.gitattributes`(sh/service/sql LF).
- 사용자 private 저장소 생성 → `git remote add origin` → **첫 push 는 사용자 터미널**(Claude 셸은 브라우저 인증 불가) → 이후 Claude 비대화 push OK. 원격에 시크릿 없음 확인. `gh` CLI 없음(불필요).
- 자동모드 메모: `git push` 를 다른 명령과 한 줄에 묶으면 분류기 차단 → 단독 실행.

**G. 3단계 VM — 보류**
- Oracle 무료티어 가입 화면에 한국 리전(서울/춘천) 미제공. 해외 리전은 KRX/KIND 해외 IP 차단 위험 → 비권장. 대안: Lightsail 서울(월 $5, 확실) / 며칠 뒤 Oracle 재시도(PAYG 업그레이드·E2.1.Micro 권장, A1 불필요) / Azure 무료 12개월. 사용자 "나중에 다시". docs/06 **부록 A** VM 생성 가이드.
- 부수 질문: 오라클@AWS 서울 기사 → 기업용 DB 상품, 무관. Lightsail $5 에 다른 앱도 올릴 수 있는가 → 가벼운 것은 가능, 게임서버는 메모리 부족, 실계좌 땐 봇 전용 권장.

**H. 집 PC 실행 편의 (커밋 cd43d2f)**
- 요청: 바탕화면 봇 실행 bat. 산출: `engine/run_bot.bat` + 바탕화면 `breakZone 봇 시작.bat`(호출용).
- 추가(요청 범위 밖 → 사용자 확인 후 유지): main.py 회전 파일 로그(`engine/logs/bot.log` 5MB×10, `LOG_DIR`), httpx 로그 WARNING. **피드백: 요청 밖 변경은 먼저 물어볼 것**(메모리 저장).
- bat 실전 실행 확인: 토큰→설정 로드→락 획득(ksh)→LIVE→명령 리스너. 강제 종료 후 락 수동 해제. 로그로 확인한 현재 설정: enabled=True, entry_rebound_pct=0.02, per_stock_krw=1,000만(사용자 의도 확인됨), add_on_drop_pct=0.05.

**I. 문서-실제 정합성 점검 (이 항목)**
- 수정: CLAUDE.md/README/engine README "설계 완료·Phase 0" 문구 → 현행. ROADMAP 진행현황 날짜·158개·Phase 0 완료기준·Phase 3 명령수신·Phase 8 작업(venv+systemd)·§3 구조도·§6 시크릿 표(secret/publishable). docs/00 §6·§7 asyncio → 동기+스레드 실제 모델. docs/01 §3.4 스레드. docs/06 §1 .env·로그·bat. PHASE0-CHECKLIST 완료 항목 체크(Supabase·CLI·주문 TR·게이트), 미실측(rate limit·동시구독 한도) 명시.
- CLAUDE.md 에 "작업 환경 메모"(스크립트 편집·push 단독·CLI·bat) 추가.

### 세션 2026-09-03 (라이브 검증 + 전략 정교화 + 사용법 문서)
- **Phase 2 완료:** 키움 왕복주문 실증(매수→미체결→취소, ord_no 0074195).
- **단계 A 통과:** 봇↔Supabase↔앱 제어 실증(하트비트·시작/정지·후보 표시).
- **앱 개선:** 설정 그룹화(기본/매수/매도/Envelope), 후보탭 해제일·D-day·정렬·상태 한글, 삼성전자 더미 삭제 + 스테일 후보 자동 정리(prune).
- **전략 정교화(사용자 규칙, 모두 조절가능):**
  1. 급등 전량매도 기준 `limit_up_pct` 설정화(하드코딩 제거).
  2. 진입 하락비율 범위→단일 `entry_drop_pct`(이 %↑ 하락 시 매수구간).
  3. 손실 한도 실현→**평가손실** `max_unrealized_loss_krw`(신규매수 중단).
  4. 후보탭 현재가 표시 버그 수정(refresh/tick에서 키움 현재가로 채움).
  5. **매수는 모든 값 확정(status ok)일 때만** — 봇이 현재가 채운 뒤 status 재계산(compute_status). partial/pending 매수 차단.
  6. **해제일 지난(D+) 종목 신규매수 제외**(매수 적기 T-5~해제일, 보유분 청산은 계속).
  7. **저가 반등 매수** `entry_rebound_pct` — 매수구간 저점 대비 반등 시 매수(falling-knife 회피, 0=즉시).
- **enabled 의미 명확화:** 매수만 on/off, 청산은 running이면 항상.
- **문서:** [사용법.md](사용법.md) 신규(실행·화면·매수/매도 조건·설정 전체·FAQ). 테스트 **137개**.
- **📱 안드로이드 폰 앱 배포 완료:** Android Studio(SDK) 설치 → APK 빌드. 빌드 이슈 2건 해결:
  ① D:프로젝트/C:펍캐시 드라이브 상이 → Kotlin 증분 상대경로 오류 → `android/gradle.properties`에 `kotlin.incremental=false`.
  ② 릴리스 APK 인터넷 권한 누락(로그인 host lookup 실패) → `AndroidManifest.xml`에 `android.permission.INTERNET`.
  → arm64 APK(17.9MB, `--split-per-abi`로 30MB↓) 폰 설치 → **로그인·실시간 정상 작동 확인.** 빌드 명령: `flutter build apk --release --split-per-abi`.

### 세션 2026-09-02 (전략 세부조정 + 문서 정합성 정리)
- **🟢 단계 A 라이브 검증 통과:** 봇 구동 → 앱 하트비트 살아남, 시작/정지 양방향 제어 작동, 후보 탭 실시간 표시. 봇↔Supabase↔앱 전체 통신·제어 실증. (주문 제외 전 시스템 OK) → 다음: 단계 B 장중 매매(내일).
- **앱 실증:** 로그인 성공 + 대시보드 실시간 데이터 확인. settings realtime 누락 → 0004 마이그레이션으로 해결. Supabase 신규 publishable key 사용.
- **설정 화면 그룹화:** 기본/매수/매도/Envelope 카드로 재구성.
- **전략 조정(사용자 확정):**
  - 급등 전량매도 기준 `limit_up_pct`(기본 29) 설정화(하드코딩 제거).
  - 진입 하락비율: 범위(min/max) → **단일 기준 `entry_drop_pct`**(이 % 이상 하락 시 매수, 상한 없음).
  - 손실 한도: 실현손실 → **평가손실(미실현) `max_unrealized_loss_krw`** 기준으로(손절 없는 전략에 맞게, 보유 전체 순평가손실 기준 신규매수 중단).
  - `min_price`(최소 매수가) 필터 확인.
- **정합성 정리:** StrategyParams ↔ docs/03 §6 ↔ 앱 설정(15개) 일치 확인. 옛 파라미터명(per_trade_krw/stop_loss/entry_drop_min·max/daily_max_loss) 문서·도구·테스트에서 정리. docs/03 §4 의사코드를 실제 동기 엔진 흐름으로 갱신. settings 테이블 개별 컬럼=레거시(파라미터는 extra) 명시. ROADMAP 진행현황표 추가.
- **테스트 132개 통과.** 커밋 22개.

### 세션 2026-09-02 (Phase 5 Flutter 앱 ✅ — 코드 완성)
- **스캐폴딩:** `flutter create app`(web+android) + supabase_flutter/flutter_riverpod/fl_chart/intl.
- **구조:** core(env·supabase 클라이언트) · data(models·repos: Realtime StreamProvider + 쓰기) · auth(login) · home(Drawer 네비) · features(dashboard/control/settings/lists).
- **기능:** Supabase 이메일 로그인 → RLS(owner=auth.uid) 하에 본인 데이터. 대시보드(status·하트비트경과·평가금·현금·당일손익), 후보/포지션/주문/이벤트 실시간 목록, 제어(start/stop/pause/resume/kill 2단계확인 → commands insert), 설정(15개 파라미터 조절 → settings.enabled + extra).
- **키:** 앱은 publishable key(`sb_publishable_…`) 사용. `env.dart`(gitignore, URL 프리필)에 키만 넣으면 됨. Supabase.initialize 는 publishableKey 파라미터.
- **검증:** `flutter analyze` 이슈 0, `flutter build web` 성공. (실행/로그인은 사용자 키 입력 후.)
- **환경:** Flutter `D:\dev\flutter` v3.47.2 사용(PATH 미등록 → 전체경로 호출).

### 세션 2026-09-02 (Phase 4 오케스트레이션 ✅ — 4조각 배선)
- **추가 조건:** `min_price`(최소 매수가, 기본 1000, 조절가능) — 신규·추가매수 공통.
- **market.py:** `is_market_open`(KST 09:00~15:30, 주말·공휴일 제외, holidays.KR).
- **engine.py(StrategyEngine):** refresh(후보수집+envelope/prev_close 계산+WS구독) · tick(sync_positions→청산평가→진입평가→하트비트) · 주문실행(_buy/_sell, relay 반영·이벤트) · kill(전량 시장가 청산) · close_position · handle_command(start/stop/pause/resume/kill/set_param/close_position) · 일손익 리셋 · 상한가 근사. **현재가는 broker.get_price(키움 WS캐시+REST)** 사용 → D-005 배선 완료(loop에서 네이버 미사용).
- **main.py:** config 검증 → 브로커 connect + relay ensure_singletons → 명령 리스너 → tick 루프(tick_seconds) + REFRESH_SEC 주기 refresh + Ctrl+C 안전종료. 시작 status=stopped(안전, 'start' 명령 대기).
- **테스트:** test_engine.py 6 + test_market.py 2 — **총 130개 통과.** import 스모크 OK.
- **남은 것:** 장중 라이브 운용 검증(모의), 상태 영속화(재시작 복원 정밀화), 오프라인 버퍼.

### 세션 2026-09-02 (Phase 4 전략 코어 ✅ — 사용자 전략 확정)
- **사용자 매매전략 확정(D-013):** 매수=하락비율 30~40% AND 현재가<envelope하단 → 분할매수(30%씩, 종목당총액 상한). 평단-7% 물타기. 매도=현재가>envelope상단 AND +15% → 50%익절, 이후 고점-5% 전량, 상한가 전량.
- **확인받은 기본값:** envelope 20일 ±10%, 분할매수 총액상한, X2 트레일링(고점기준), 주문=지정가.
- **구현(순수 코어):** `src/strategy/` — params(StrategyParams, settings.extra 로드) · indicators(compute_envelope) · state(PositionState 분할추적) · rules(should_enter E1/E2, should_exit X1/X2/X3) · risk(ok_buy/ok_sell 가드, real클램프 골격).
- **테스트:** test_strategy.py 29개 — **총 120개 통과.**
- **남은 Phase 4:** engine.py(오케스트레이션: 후보→규칙→리스크→broker 주문→relay 반영) + main.py(KST 스케줄러·상태기계·commands 처리). candidates 현재가 네이버→키움 배선.
- docs/03 §2 전략 명세 확정 반영, DECISIONS D-013.

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
| D-005 | 현재가 소스: 키움 실시간 WS(폴백 네이버), 과거종가 pykrx 유지 | ✅ 확정·배선 완료 |
| D-006 | 키움 MCP 서버는 **개발 보조**용. **봇 매매경로는 REST/WS 직접 호출** | ✅ 확정 |
| D-007 | Phase 2 브로커 = **자체구현**(kiwoom-client 참조) | ✅ 확정(2026-09-02) |
| D-008 | 자동매매 조건은 Phase 4에서 확정 + 앱에서 조절 | ✅ 이행(D-013으로 구체화, 앱 설정 15개) |
| D-009 | 문서 관리: PROGRESS/DECISIONS로 세션 간 인수인계 | ✅ 확정 |
| D-010 | Python 3.12 설치(3.11+ 요건 충족) | ✅ 확정 |
| D-011 | 브로커 = 동기(requests) REST + 스레드 WebSocket | ✅ 확정 |
| D-012 | 명령 수신 = 폴링(스레드 1.5초), Realtime 후속 | ✅ 확정 |
| D-013 | 매매 전략(진입/청산) 사용자 정의 — 수치 전부 조절가능 | 🟡 초안(Phase 6 백테스트로 튜닝 후 확정) |
| D-014 | 단일 사용자 유지(다중 사용자 미지원) | ✅ 확정(사용자, 2026-09-03) |
| D-015 | 클라우드 이관을 장기 테스트 앞으로(venv+systemd, 국내 VM, git 재배포) | ✅ 확정(사용자, 2026-09-03) |

---

## 💻 환경 현황 (2026-09-03)

| 런타임 | 상태 | 위치/버전 | 필요 Phase |
|---|---|---|---|
| Python | ✅ | 3.12.10 + `engine/.venv` | 1+ |
| Git | ✅ | 2.55.0 | 0+ |
| Flutter | ✅ (PATH 미등록 → 전체경로 호출) | `D:\dev\flutter` 3.47.2 | 5 |
| Android Studio/SDK | ✅ (2026-09-03 설치) | APK 빌드용 | 5 |
| Supabase CLI | ✅ 설치+login+link 완료(2026-09-03). 이력 repair 0001~0004 applied, `db push --dry-run` up to date | `D:\dev\supabase` v2.116.0 (PATH 등록, 새 터미널부터). 연결 후 `db push`로 Claude가 마이그레이션 직접 적용 | 3+ |
| Docker | ❌ | — | 8 |

**키/환경파일:** `engine/.env`(키움 모의 + Supabase secret), `app/lib/core/env.dart`(publishable key) 모두 존재(gitignore).
**폴더:** `breakZone/`(참조·수정금지) 와 `breakZoneAutoApp/`(작업) 형제 배치. 이식은 스냅샷 복사.

---

## 📌 열려있는 질문 / 보류

- **전략 수치 확정** — D-013은 초안. Phase 6 백테스트(`backtest/runner.py` 미작성)로 튜닝 후 확정.
- **저가 반등 × 진입기준 상호작용** — 반등(`entry_rebound_pct`) 후 현재가 하락비율이 `entry_drop_pct` 안쪽으로 올라오면 **매수 안 됨**(현재가 기준 게이트가 먼저 적용, 저점도 리셋). 기준 30%·반등 2%면 실효 기준 ≈ 31.4%↓ 저점에서만 매수. "저점이 구간 안이었으면 반등 후 기준 이탈해도 매수" 로 바꿀지 사용자 판단 대기(2026-09-03).
- **백그라운드 푸시(FCM)** — Phase 5-B 미채택(보류). 필요 시 재검토.
- **키움 정정 TR(kt10002)** 미검증 — 취소+재주문으로 대체 가능.
- **오프라인 버퍼**(네트워크 끊김 시 밀린 상태 재전송) — 후속. (전략상태 영속화는 2026-09-03 완료)

---

## 🔧 세션 종료 시 갱신 규칙 (Claude용 메모)

매 세션 끝에 반드시:
1. §한눈에 표의 날짜·현재 Phase 갱신
2. §다음에 할 일 최신화
3. §세션 로그에 이번 세션 항목 추가(무엇을·왜·결과)
4. 새 결정이 있으면 §결정 요약 표 + DECISIONS.md 추가
5. 관련 체크리스트(PHASE0-CHECKLIST 등) 체크박스 갱신

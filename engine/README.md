# engine — 전략 엔진(봇)

KRX 경고주 분석 + 키움 REST 자동매매 봇. 상세 설계는 [../ROADMAP.md](../ROADMAP.md), [../docs/](../docs/).

## 지금 상태 (Phase 0)
아직 본 코드 없음. 키움 모의 연결 확인용 스모크 테스트만 있음.

## Phase 0 — 키움 연결 확인
```powershell
cd engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # 그리고 .env 에 모의 App Key/Secret/계좌번호 입력
python tools/check_kiwoom_token.py
```
성공하면 "접근토큰 발급 성공"이 출력된다 = Phase 0 핵심 게이트 통과.

> `.env` 는 절대 커밋 금지(.gitignore 처리). 키/토큰은 마스킹 출력만.

## 앞으로 (요약)
- Phase 1: `src/analysis/` 에 breakZone 분석 로직 이식 → 후보 산출.
- Phase 2: `src/broker/` 키움 어댑터.
- Phase 3: `src/relay/` Supabase 동기화.
- Phase 4: `src/strategy/` 매매 루프 + 리스크 가드.

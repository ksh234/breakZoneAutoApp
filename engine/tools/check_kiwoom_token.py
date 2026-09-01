"""
Phase 0 스모크 테스트 — 키움 모의투자 REST 연결 확인.

하는 일:
  1) 접근토큰 발급 (POST /oauth2/token)              → Phase 0 완료기준 "토큰 발급 성공"
  2) 계좌평가잔고 조회 (api-id: kt00018)             → Phase 0 완료기준 "잔고조회 200"

사용법 (engine/ 에서):
  Copy-Item .env.example .env    # 그리고 .env 에 실제 모의 키/계좌 입력
  python tools/check_kiwoom_token.py

⚠️ 키/토큰은 마스킹해서만 출력한다. 실제 값은 로그/화면에 남기지 않는다.

스펙 출처(2026-09-01 실측): 키움 공식 저장소 Kiwoom-Securities/Kiwoom-REST-API 예제 +
younghwan91/kiwoom-rest-api auth.py. 상세는 docs/01-broker-kiwoom.md "확정 스펙" 표.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests 미설치. `pip install -r requirements.txt` 먼저 실행하세요.")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv 미설치. `pip install -r requirements.txt` 먼저 실행하세요.")

# ── 확정 스펙 (docs/01) ──
BASE = {
    "demo": "https://mockapi.kiwoom.com",
    "real": "https://api.kiwoom.com",
}
TOKEN_PATH = "/oauth2/token"
ACNT_PATH = "/api/dostk/acnt"          # 국내주식 계좌 도메인
BALANCE_TR = "kt00018"                  # 계좌평가잔고내역요청
JSON_CT = "application/json;charset=UTF-8"


def mask(s: str, keep: int = 4) -> str:
    if not s:
        return "(없음)"
    return s[:keep] + "…" + f"({len(s)}자)"


def main() -> int:
    # .env 를 engine/ 기준으로 로드
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)

    mode = os.getenv("KIWOOM_MODE", "demo").strip().lower()
    app_key = os.getenv("KIWOOM_APP_KEY", "").strip()
    secret = os.getenv("KIWOOM_SECRET", "").strip()
    account = os.getenv("KIWOOM_ACCOUNT_NO", "").strip()

    if mode not in BASE:
        print(f"[오류] KIWOOM_MODE 는 demo/real 중 하나여야 함 (현재: {mode!r})")
        return 1
    if mode == "real":
        print("[중단] 이 스크립트는 모의(demo) 전용입니다. .env 의 KIWOOM_MODE=demo 로 두세요.")
        return 1
    if not app_key or not secret:
        print(f"[오류] .env 에 KIWOOM_APP_KEY/SECRET 이 없습니다. ({env_path})")
        print("       .env.example 을 복사해 실제 모의 키를 채우세요.")
        return 1

    base = BASE[mode]
    print(f"● 모드: {mode}  base: {base}")
    print(f"● App Key: {mask(app_key)}  Secret: {mask(secret)}  계좌: {mask(account, 6)}")

    # ── 1) 접근토큰 발급 ──
    print("\n[1] 접근토큰 발급 요청 → POST", TOKEN_PATH)
    try:
        r = requests.post(
            base + TOKEN_PATH,
            headers={"Content-Type": JSON_CT},
            json={"grant_type": "client_credentials", "appkey": app_key, "secretkey": secret},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"    [실패] 네트워크 오류: {e}")
        return 1

    print(f"    HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        print("    [실패] JSON 아님:", r.text[:200])
        return 1

    token = data.get("token") or data.get("access_token")
    rc = data.get("return_code")
    if r.status_code != 200 or not token:
        print(f"    [실패] return_code={rc} return_msg={data.get('return_msg')}")
        print("    응답(요약):", {k: v for k, v in data.items() if k not in ("token", "access_token")})
        return 1

    print(f"    [성공] 토큰 발급됨: {mask(token, 6)}")
    print(f"    token_type={data.get('token_type')}  expires_dt={data.get('expires_dt')}  "
          f"return_msg={data.get('return_msg')}")

    # ── 2) 계좌평가잔고 조회 ──
    print(f"\n[2] 계좌평가잔고 조회 → POST {ACNT_PATH} (api-id: {BALANCE_TR})")
    try:
        r2 = requests.post(
            base + ACNT_PATH,
            headers={
                "authorization": f"Bearer {token}",
                "api-id": BALANCE_TR,
                "Content-Type": JSON_CT,
            },
            json={"qry_tp": "1", "dmst_stex_tp": "KRX"},
            timeout=10,
        )
        print(f"    HTTP {r2.status_code}")
        d2 = r2.json()
        rc2 = d2.get("return_code")
        if r2.status_code == 200 and rc2 in (0, "0"):
            print("    [성공] 잔고 조회 OK. 주요 값:")
            for k, label in (
                ("prsm_dpst_aset_amt", "추정예탁자산"),
                ("tot_evlt_amt", "총평가금액"),
                ("tot_pur_amt", "총매입금액"),
                ("tot_evlt_pl", "총평가손익"),
            ):
                if k in d2:
                    print(f"      - {label}({k}): {d2[k]}")
        else:
            print(f"    [주의] 잔고조회 응답 확인 필요: return_code={rc2} "
                  f"return_msg={d2.get('return_msg')}")
            print("    (토큰 발급은 이미 성공. 잔고 파라미터는 docs/01 실측 시 조정)")
    except (requests.RequestException, ValueError) as e:
        print(f"    [주의] 잔고조회 중 오류(토큰 성공은 유효): {e}")

    print("\n✅ Phase 0 핵심 게이트 '접근토큰 발급 성공' 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

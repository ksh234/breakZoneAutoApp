r"""Phase 3 스모크 테스트 — Supabase 중계 동작 확인.

하는 일:
  1) 싱글턴 보장(settings/bot_state)
  2) bot_state 하트비트 push
  3) 더미 후보 upsert + 이벤트 insert
  4) settings 로드 출력
  --listen: 명령 리스너를 20초 실행 (대시보드 commands 에 행 추가하면 반응)

사용법 (engine/ 에서, .env 에 SUPABASE_* 채운 상태):
    .\.venv\Scripts\python.exe tools\check_supabase.py
    .\.venv\Scripts\python.exe tools\check_supabase.py --listen
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402
from src.analysis.candidates import Candidate  # noqa: E402
from src.relay import Relay  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true", help="명령 리스너 20초 실행")
    args = ap.parse_args()

    try:
        config.require("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_OWNER_UUID")
    except RuntimeError as e:
        print(f"[오류] {e}")
        return 1

    relay = Relay(config.SUPABASE_URL, config.SUPABASE_SECRET_KEY, config.SUPABASE_OWNER_UUID)
    print(f"● owner={config.SUPABASE_OWNER_UUID[:8]}…  url={config.SUPABASE_URL}")

    print("[1] 싱글턴 보장(settings/bot_state)…")
    relay.ensure_singletons()
    print("    OK")

    print("[2] bot_state 하트비트 push…")
    relay.push_bot_state(status="stopped", market_open=False, equity=0, cash=0,
                         positions_cnt=0, day_pnl=0, message="Phase3 스모크 테스트")
    print("    OK")

    print("[3] 더미 후보 upsert + 이벤트 insert…")
    dummy = Candidate(
        code="005930", name="삼성전자(테스트)", designated_date=date(2026, 4, 1),
        release_date=date(2026, 4, 16), t5_close=70000, t15_close=35000,
        recent_15_high=72000, release_amount=70000, current_price=68000,
        drop_ratio=3, status="ok", signal="watch",
    )
    relay.upsert_candidates([dummy])
    relay.insert_event("test", "info", "스모크 테스트", "relay 동작 확인")
    print("    OK")

    print("[4] settings 로드(StrategyParams)…")
    from src.strategy.params import StrategyParams
    p = StrategyParams.from_settings(relay.load_settings())
    print(f"    enabled={p.enabled} mode={p.mode} entry_drop_pct={p.entry_drop_pct} "
          f"per_stock_krw={p.per_stock_krw} max_positions={p.max_positions}")

    print("\n✅ Supabase 중계 동작 확인. 대시보드 Table editor 에서 bot_state/candidates/events 확인 가능.")

    if args.listen:
        print("\n[5] 명령 리스너 20초 실행 — 대시보드 commands 에 "
              "{owner, type:'start', status:'pending'} 행을 넣어보세요.")

        def handle(row):
            print(f"    ▶ 명령 수신: type={row['type']} payload={row.get('payload')}")
            return f"handled {row['type']}"

        relay.start_command_listener(handle, interval=1.5)
        time.sleep(20)
        relay.stop()
        print("    리스너 종료.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

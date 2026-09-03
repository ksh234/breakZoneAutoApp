r"""봇 엔트리 — 스케줄러 루프 + 상태기계 + 명령 구독. docs/00 §4, docs/03 §4.

실행(engine/):
    .\.venv\Scripts\python.exe -m src.main

- 시작 시 status=stopped(안전). 앱/commands 의 'start' 명령으로 매매 시작.
- tick 주기(params.tick_seconds)로 매매 평가, REFRESH_SEC 마다 후보/지표 갱신(장중).
- settings 는 시작 시 + 'set_param' 명령 시 + PARAMS_RELOAD_SEC(30초) 주기로 재로드(앱 저장 반영).
- Ctrl+C 로 안전 종료(WS·명령리스너 정리).
"""
from __future__ import annotations

import logging
import time

from . import config
from .broker import create_broker
from .relay import Relay
from .strategy.engine import StrategyEngine
from .strategy.market import is_market_open
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
REFRESH_SEC = 600  # 후보/지표 갱신 주기(10분)


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("main")

    try:
        config.require("KIWOOM_APP_KEY", "KIWOOM_SECRET",
                       "SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_OWNER_UUID")
    except RuntimeError as e:
        log.error("%s", e)
        return 1

    broker = create_broker(config.KIWOOM_APP_KEY, config.KIWOOM_SECRET,
                           config.KIWOOM_ACCOUNT_NO, mode=config.KIWOOM_MODE)
    relay = Relay(config.SUPABASE_URL, config.SUPABASE_SECRET_KEY, config.SUPABASE_OWNER_UUID)

    log.info("키움 연결(%s) + Supabase 중계 초기화…", config.KIWOOM_MODE)
    broker.connect()
    relay.ensure_singletons()

    engine = StrategyEngine(broker, relay)
    engine.load_params()
    relay.start_command_listener(engine.handle_command)
    log.info("명령 리스너 시작. status=stopped (앱에서 'start' 명령 대기).")

    # 초기 후보 1회 수집(장외여도 후보/지표는 준비)
    try:
        engine.refresh()
    except Exception:
        log.exception("초기 refresh 실패(계속 진행)")
    last_refresh = time.monotonic()

    log.info("메인 루프 시작 (tick=%ss, refresh=%ss)", engine.params.tick_seconds, REFRESH_SEC)
    try:
        while True:
            try:
                engine.tick()
                now = datetime.now(KST)
                if is_market_open(now) and time.monotonic() - last_refresh > REFRESH_SEC:
                    engine.refresh()
                    last_refresh = time.monotonic()
            except Exception:
                log.exception("tick 오류(루프 유지)")
                engine._emit("error", "high", "tick 오류", "루프는 계속됨 — 로그 확인")
            time.sleep(max(1, engine.params.tick_seconds))
    except KeyboardInterrupt:
        log.info("종료 신호 수신 — 정리 중…")
    finally:
        engine._emit("state", "info", "봇 종료", "프로세스 정리")
        try:
            relay.stop()
        except Exception:
            pass
        try:
            broker.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

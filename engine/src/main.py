r"""봇 엔트리 — 스케줄러 루프 + 상태기계 + 명령 구독 + 이중 실행 락. docs/00 §4, docs/03 §4, docs/05 §4.

실행(engine/):
    .\.venv\Scripts\python.exe -m src.main

- 시작 시 status=stopped(안전). 앱/commands 의 'start' 명령으로 매매 시작.
- tick 주기(params.tick_seconds)로 매매 평가, REFRESH_SEC 마다 후보/지표 갱신(장중).
- settings 는 시작 시 + 'set_param' 명령 시 + PARAMS_RELOAD_SEC(30초) 주기로 재로드(앱 저장 반영).
- 이중 실행 방지: bot_lock 획득한 인스턴스만 LIVE(주문·Supabase 쓰기·명령 처리).
  미획득 시 관찰 모드로 대기하며 BOT_LOCK_RENEW_SEC 마다 재시도(보유자 하트비트 stale → 승계).
- BOT_DRY_RUN=1: 락과 무관하게 항상 관찰 모드(PC 에서 새 코드 장중 관찰용). status=running 으로 판정 로그.
- Ctrl+C 로 안전 종료(락 해제·WS·명령리스너 정리).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from . import config
from .broker import create_broker
from .relay import Relay
from .strategy.engine import StrategyEngine
from .strategy.market import is_market_open

KST = timezone(timedelta(hours=9))
REFRESH_SEC = 600  # 후보/지표 갱신 주기(10분)


class LockKeeper:
    """락 획득/갱신/상실을 엔진 LIVE 모드 전환에 연결."""

    def __init__(self, relay: Relay, engine: StrategyEngine, holder: str, stale_sec: int, renew_sec: int):
        self.relay, self.engine, self.holder = relay, engine, holder
        self.stale_sec, self.renew_sec = stale_sec, renew_sec
        self.held = False
        self._last = 0.0
        self.log = logging.getLogger("lock")

    def _try(self) -> bool:
        try:
            return self.relay.acquire_lock(self.holder, self.stale_sec)
        except Exception as e:
            self.log.warning("락 호출 실패: %s", e)
            return False

    def go_live(self) -> None:
        """락 획득 직후 1회: 싱글턴 보장 → 상태 복원 → 명령 리스너."""
        self.engine.set_live(True, f"락 획득 holder={self.holder}")
        self.relay.ensure_singletons()
        self.engine.restore_state()
        self.relay.start_command_listener(self.engine.handle_command)
        self.engine._emit("state", "info", "봇 LIVE", f"락 획득: {self.holder}")

    def go_observe(self, why: str) -> None:
        self.engine._emit("error", "critical", "락 상실 → 관찰 모드", why)  # 전환 전(LIVE relay)에 기록
        self.engine.set_live(False, why)
        self.relay.stop()  # 명령 리스너 중단(다른 인스턴스가 처리)

    def start(self) -> bool:
        self.held = self._try()
        self._last = time.monotonic()
        if self.held:
            self.go_live()
        else:
            self.engine.set_live(False, "락 미획득 — 다른 봇 인스턴스 실행 중. 관찰 모드로 대기(주문·쓰기 없음)")
        return self.held

    def tick(self) -> None:
        if time.monotonic() - self._last < self.renew_sec:
            return
        self._last = time.monotonic()
        ok = self._try()
        if ok and not self.held:
            self.held = True
            self.log.warning("락 승계 성공 → LIVE")
            self.go_live()
        elif not ok and self.held:
            self.held = False
            self.go_observe("락 갱신 실패(다른 인스턴스가 승계?) — 주문 중단")

    def release(self) -> None:
        if self.held:
            try:
                self.relay.release_lock(self.holder)
            except Exception:
                pass


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

    log.info("키움 연결(%s) + Supabase 중계 초기화… holder=%s dry_run=%s",
             config.KIWOOM_MODE, config.BOT_HOLDER_ID, config.BOT_DRY_RUN)
    broker.connect()

    engine = StrategyEngine(broker, relay)
    lock: LockKeeper | None = None
    if config.BOT_DRY_RUN:
        engine.set_live(False, "BOT_DRY_RUN=1 — 주문·Supabase 쓰기 금지, 판정 로그만")
        engine.load_params()
        engine.restore_state()          # 읽기만(실 봇 상태 기준으로 관찰)
        engine.status = "running"       # 명령 없이 바로 판정 루프
        log.warning("★ DRY-RUN 모드. 로그의 [DRY] 판정만 참고. 실제 주문 없음.")
    else:
        lock = LockKeeper(relay, engine, config.BOT_HOLDER_ID,
                          config.BOT_LOCK_STALE_SEC, config.BOT_LOCK_RENEW_SEC)
        engine.load_params()
        if lock.start():
            log.info("락 획득(%s). 명령 리스너 시작. status=stopped (앱에서 'start' 명령 대기).", config.BOT_HOLDER_ID)
        else:
            log.warning("★ 락 미획득 — 관찰 모드. %d초마다 재시도(보유자 하트비트 %d초 stale 시 승계).",
                        config.BOT_LOCK_RENEW_SEC, config.BOT_LOCK_STALE_SEC)

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
                if lock:
                    lock.tick()
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
        if lock:
            lock.release()
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

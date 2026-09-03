r"""Phase 2 통합 테스트 — 키움 모의계좌 왕복 시나리오 (수동 실행, 네트워크 필요).

기본(읽기 전용): 토큰 발급 → 잔고 → 현재가.
--order 붙이면: 체결 안 될 저가 지정가 매수 1주 → 미체결 확인 → 취소 (모의계좌).
--ws 붙이면: 삼성전자 실시간 체결가 10초 수신.

사용법 (engine/ 에서, .env 에 모의 키 채운 상태):
    .\.venv\Scripts\python.exe tools\it_kiwoom.py            # 읽기 전용
    .\.venv\Scripts\python.exe tools\it_kiwoom.py --order    # 왕복 주문까지
    .\.venv\Scripts\python.exe tools\it_kiwoom.py --order --ws

⚠️ 모의(demo) 전용. .env 의 KIWOOM_MODE 가 real 이면 중단한다.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # engine/ 를 import 경로에
from src.broker import OrderType, Side, create_broker  # noqa: E402
from src.broker.errors import BrokerError  # noqa: E402

TEST_CODE = "005930"  # 삼성전자


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", action="store_true", help="저가 지정가 매수→미체결확인→취소 왕복")
    ap.add_argument("--ws", action="store_true", help="실시간 체결가 10초 수신")
    args = ap.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    mode = os.getenv("KIWOOM_MODE", "demo").strip().lower()
    if mode != "demo":
        print("[중단] 모의(demo) 전용 스크립트입니다. .env KIWOOM_MODE=demo 로 두세요.")
        return 1
    app_key = os.getenv("KIWOOM_APP_KEY", "").strip()
    secret = os.getenv("KIWOOM_SECRET", "").strip()
    account = os.getenv("KIWOOM_ACCOUNT_NO", "").strip()
    if not app_key or not secret:
        print("[오류] .env 에 KIWOOM_APP_KEY/SECRET 이 없습니다.")
        return 1

    broker = create_broker(app_key, secret, account, mode="demo")

    print("[1] 토큰 발급(connect)…")
    try:
        broker.connect()
    except BrokerError as e:
        print(f"    [실패] {e}")
        return 1
    print("    OK")

    print("[2] 잔고 조회…")
    try:
        bal = broker.get_balance()
        print(f"    추정예탁자산(equity)={bal.equity:,}  주식평가={bal.stock_value:,}  주문가능현금(근사)={bal.cash:,}")
    except BrokerError as e:
        print(f"    [실패] {e}")

    print(f"[3] 현재가 조회 {TEST_CODE}…")
    price = broker.get_price(TEST_CODE)
    print(f"    현재가 = {price}")

    print("[4] 보유 포지션…")
    try:
        positions = broker.get_positions()
        if not positions:
            print("    (없음)")
        for p in positions:
            print(f"    - {p.name}({p.code}) {p.qty}주 평단 {p.avg_price:,} 현재 {p.current_price:,} 손익 {p.pnl:,}")
    except BrokerError as e:
        print(f"    [실패] {e}")

    if args.order:
        _order_roundtrip(broker, price)

    if args.ws:
        _ws_test(broker)

    broker.close()
    print("\n✅ 통합 테스트 종료.")
    return 0


def _order_roundtrip(broker, price):
    print("\n[5] 왕복 주문 (체결 안 될 저가 지정가 매수 1주 → 취소)")
    if not price:
        print("    현재가 조회 실패로 주문 스킵")
        return
    # 호가단위(KRX 가격대별). 현재가 -10% 를 호가단위로 내림 → 상/하한가(±30%) 이내 & 저가라 미체결.
    def _tick(p):
        for cap, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
            if p < cap:
                return t
        return 1000
    tick = _tick(price)
    limit = max(tick, (int(price * 0.90) // tick) * tick)
    print(f"    매수 지정가 {limit:,}원 x1주 (현재가 -10%, 호가단위 {tick}, 체결 안 되게 저가)")
    try:
        order = broker.place_order(TEST_CODE, Side.BUY, 1, OrderType.LIMIT, price=limit,
                                   name="삼성전자", reason="it_test")
        print(f"    주문번호 = {order.broker_order_id}")
    except BrokerError as e:
        print(f"    [실패] 주문 거부: {e}")
        return

    time.sleep(1)
    print("    미체결 조회…")
    try:
        unfilled = broker.get_unfilled_orders()
        mine = [u for u in unfilled if u["ord_no"] == order.broker_order_id]
        print(f"    미체결 {len(unfilled)}건 (내 주문 {len(mine)}건): {mine or unfilled[:3]}")
    except BrokerError as e:
        print(f"    [주의] 미체결 조회 실패: {e}")

    print("    주문 취소…")
    try:
        broker.cancel(order)
        print("    취소 요청 완료")
    except BrokerError as e:
        print(f"    [실패] 취소: {e}")


def _ws_test(broker):
    print("\n[6] 실시간 체결가 10초 수신 (삼성전자)")
    got = []
    broker.subscribe_realtime([TEST_CODE], lambda code, p: got.append((code, p)) or print(f"    tick {code} {p}"))
    time.sleep(10)
    print(f"    수신 {len(got)}건 (장중이 아니면 0건일 수 있음)")


if __name__ == "__main__":
    raise SystemExit(main())

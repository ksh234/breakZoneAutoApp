-- 0008_bot_state_balance_fields.sql — 대시보드 잔고 항목을 영웅문 정의와 맞춤 (2026-09-23)
-- equity=총자산(추정예탁자산), cash=주문가능금액(kt00001 ord_alow_amt) 로 의미 확정 + 아래 3개 추가.
alter table bot_state
  add column if not exists stock_value    bigint,   -- 주식 평가금 (kt00018 tot_evlt_amt)
  add column if not exists deposit        bigint,   -- 예수금 (kt00001 entr)
  add column if not exists unrealized_pnl bigint;   -- 총평가손익 (kt00018 tot_evlt_pl)

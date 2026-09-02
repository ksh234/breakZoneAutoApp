-- 0003_realtime.sql — Realtime publication (docs/02 §4)
-- 앱: bot_state/candidates/positions/orders/events 구독 → UI 실시간 갱신.
-- 봇: commands 구독(또는 폴링) → 명령 실행.
-- (이미 publication 에 있으면 오류 무시하도록 개별 처리)

do $$
declare t text;
begin
  foreach t in array array['bot_state','candidates','positions','orders','events','commands']
  loop
    begin
      execute format('alter publication supabase_realtime add table %I', t);
    exception when duplicate_object then
      null;  -- 이미 추가됨
    end;
  end loop;
end $$;

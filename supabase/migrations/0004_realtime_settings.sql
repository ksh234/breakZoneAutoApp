-- 0004_realtime_settings.sql — settings 테이블 Realtime 추가.
-- 앱 설정화면이 settings 를 실시간 구독하므로 publication 에 포함해야 함.
-- (0003 에서 누락 → 이미 마이그레이션한 DB용 보정. 신규 설치는 0003 에 포함됨)

do $$
begin
  alter publication supabase_realtime add table settings;
exception when duplicate_object then
  null;  -- 이미 추가됨
end $$;

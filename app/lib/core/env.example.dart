// 이 파일을 복사해 env.dart 로 만들고 실제 값을 채운다. (env.dart 는 .gitignore 처리)
//   supabaseUrl: Supabase Project URL
//   supabaseAnonKey: publishable key (sb_publishable_…)  ← 공개 가능(RLS로 보호). service_role 절대 금지.
class Env {
  static const String supabaseUrl = 'https://YOUR_REF.supabase.co';
  static const String supabaseAnonKey = 'sb_publishable_XXXXXXXX';
}

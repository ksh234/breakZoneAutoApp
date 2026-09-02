import 'package:supabase_flutter/supabase_flutter.dart';

/// 전역 Supabase 클라이언트 (main 에서 initialize 후 사용).
SupabaseClient get supabase => Supabase.instance.client;

/// 현재 로그인 사용자 id (owner). 미로그인 시 빈 문자열.
String get ownerId => supabase.auth.currentUser?.id ?? '';

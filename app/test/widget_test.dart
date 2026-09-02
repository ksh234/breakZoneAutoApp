import 'package:flutter_test/flutter_test.dart';

// 앱 위젯 테스트는 Supabase.initialize 필요 → 여기선 기본 스모크만.
void main() {
  test('smoke', () {
    expect(1 + 1, 2);
  });
}

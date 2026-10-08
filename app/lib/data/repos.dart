import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/supabase.dart';
import 'models.dart';

/// 끊겨도 스스로 다시 붙는 스트림(2026-10-08). 오류(폰 네트워크 끊김 등)를 한 번 알린 뒤
/// 2→4→…→30초 간격으로 재구독. 데이터를 다시 받으면 간격 초기화.
Stream<T> _resilient<T>(Stream<T> Function() make) async* {
  var delay = 2;
  while (true) {
    try {
      await for (final v in make()) {
        delay = 2;
        yield v;
      }
      return;
    } catch (e, st) {
      yield* Stream<T>.error(e, st);
    }
    await Future<void>.delayed(Duration(seconds: delay));
    delay = delay >= 30 ? 30 : delay * 2;
  }
}

/// 앱 복귀 시 일괄 새로고침용(home_screen).
void refreshAllStreams(WidgetRef ref) {
  for (final p in [botStateProvider, settingsProvider, candidatesProvider, positionsProvider,
                   ordersProvider, eventsProvider, tradesProvider]) {
    ref.invalidate(p);
  }
}

// ── Realtime 스트림 프로바이더 (UI 자동 갱신) ──
final botStateProvider = StreamProvider.autoDispose<BotState?>((ref) {
  return _resilient(() => supabase.from('bot_state').stream(primaryKey: ['id'])
      .map((rows) => rows.isEmpty ? null : BotState.fromMap(rows.first)));
});

final settingsProvider = StreamProvider.autoDispose<Settings?>((ref) {
  return _resilient(() => supabase.from('settings').stream(primaryKey: ['id'])
      .map((rows) => rows.isEmpty ? null : Settings.fromMap(rows.first)));
});

final candidatesProvider = StreamProvider.autoDispose<List<Candidate>>((ref) {
  return _resilient(() => supabase.from('candidates').stream(primaryKey: ['owner', 'code'])
      .map((rows) => rows.map(Candidate.fromMap).toList()));
});

final positionsProvider = StreamProvider.autoDispose<List<Position>>((ref) {
  return _resilient(() => supabase.from('positions').stream(primaryKey: ['owner', 'code'])
      .map((rows) => rows.map(Position.fromMap).toList()));
});

final ordersProvider = StreamProvider.autoDispose<List<OrderRow>>((ref) {
  return _resilient(() => supabase.from('orders').stream(primaryKey: ['id'])
      .order('created_at', ascending: false).limit(50)
      .map((rows) => rows.map(OrderRow.fromMap).toList()));
});

final eventsProvider = StreamProvider.autoDispose<List<EventRow>>((ref) {
  return _resilient(() => supabase.from('events').stream(primaryKey: ['id'])
      .order('created_at', ascending: false).limit(50)
      .map((rows) => rows.map(EventRow.fromMap).toList()));
});

final tradesProvider = StreamProvider.autoDispose<List<Trade>>((ref) {
  return _resilient(() => supabase.from('trades').stream(primaryKey: ['id'])
      .order('first_buy_at', ascending: false).limit(200)
      .map((rows) => rows.map(Trade.fromMap).toList()));
});

// ── 쓰기 (제어) ──
Future<void> sendCommand(String type, {Map<String, dynamic>? payload}) async {
  await supabase.from('commands').insert({
    'owner': ownerId, 'type': type, 'payload': payload ?? {}, 'status': 'pending',
  });
}

Future<void> saveSettings({required bool enabled, required Map<String, dynamic> extra}) async {
  await supabase.from('settings').update({'enabled': enabled, 'extra': extra}).eq('id', 1);
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/supabase.dart';
import 'models.dart';

// ── Realtime 스트림 프로바이더 (UI 자동 갱신) ──
final botStateProvider = StreamProvider.autoDispose<BotState?>((ref) {
  return supabase.from('bot_state').stream(primaryKey: ['id'])
      .map((rows) => rows.isEmpty ? null : BotState.fromMap(rows.first));
});

final settingsProvider = StreamProvider.autoDispose<Settings?>((ref) {
  return supabase.from('settings').stream(primaryKey: ['id'])
      .map((rows) => rows.isEmpty ? null : Settings.fromMap(rows.first));
});

final candidatesProvider = StreamProvider.autoDispose<List<Candidate>>((ref) {
  return supabase.from('candidates').stream(primaryKey: ['owner', 'code'])
      .map((rows) => rows.map(Candidate.fromMap).toList());
});

final positionsProvider = StreamProvider.autoDispose<List<Position>>((ref) {
  return supabase.from('positions').stream(primaryKey: ['owner', 'code'])
      .map((rows) => rows.map(Position.fromMap).toList());
});

final ordersProvider = StreamProvider.autoDispose<List<OrderRow>>((ref) {
  return supabase.from('orders').stream(primaryKey: ['id'])
      .order('created_at', ascending: false).limit(50)
      .map((rows) => rows.map(OrderRow.fromMap).toList());
});

final eventsProvider = StreamProvider.autoDispose<List<EventRow>>((ref) {
  return supabase.from('events').stream(primaryKey: ['id'])
      .order('created_at', ascending: false).limit(50)
      .map((rows) => rows.map(EventRow.fromMap).toList());
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

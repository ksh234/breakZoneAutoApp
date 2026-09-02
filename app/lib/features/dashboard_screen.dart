import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../data/models.dart';
import '../data/repos.dart';

final _won = NumberFormat('#,###');

Color statusColor(String s) => switch (s) {
  'running' => Colors.green,
  'paused' => Colors.orange,
  'stopping' => Colors.orange,
  'error' => Colors.red,
  _ => Colors.grey,
};

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botStateProvider);
    final positions = ref.watch(positionsProvider);
    final orders = ref.watch(ordersProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(botStateProvider),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          bot.when(
            data: (b) => _BotCard(b),
            loading: () => const Card(child: ListTile(title: Text('불러오는 중…'))),
            error: (e, _) => Card(child: ListTile(
                title: const Text('상태 조회 오류'), subtitle: Text('$e'))),
          ),
          const SizedBox(height: 12),
          Row(children: [
            _MiniStat('보유 종목', positions.maybeWhen(
                data: (p) => '${p.length}', orElse: () => '-')),
            _MiniStat('오늘 주문', orders.maybeWhen(
                data: (o) => '${o.length}', orElse: () => '-')),
          ]),
        ],
      ),
    );
  }
}

class _BotCard extends StatelessWidget {
  final BotState? b;
  const _BotCard(this.b);
  @override
  Widget build(BuildContext context) {
    if (b == null) {
      return const Card(child: Padding(padding: EdgeInsets.all(16),
          child: Text('봇 상태 없음 (아직 하트비트 없음)')));
    }
    final s = b!;
    final elapsed = s.heartbeatAt == null
        ? '-' : '${DateTime.now().difference(s.heartbeatAt!).inSeconds}초 전';
    final stale = s.heartbeatAt != null &&
        DateTime.now().difference(s.heartbeatAt!).inSeconds > 90;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(width: 12, height: 12, decoration: BoxDecoration(
                color: statusColor(s.status), shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(s.status.toUpperCase(),
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const Spacer(),
            Text(s.marketOpen ? '장중' : '장외',
                style: TextStyle(color: s.marketOpen ? Colors.green : Colors.grey)),
          ]),
          const SizedBox(height: 4),
          Text('하트비트 $elapsed',
              style: TextStyle(color: stale ? Colors.red : Colors.grey, fontSize: 12)),
          if (stale) const Text('⚠ 연결 끊김 의심',
              style: TextStyle(color: Colors.red, fontSize: 12)),
          const Divider(height: 20),
          _row('평가금', '${_won.format(s.equity)} 원'),
          _row('주문가능현금', '${_won.format(s.cash)} 원'),
          _row('당일손익', '${s.dayPnl >= 0 ? '+' : ''}${_won.format(s.dayPnl)} 원',
              color: s.dayPnl >= 0 ? Colors.green : Colors.red),
          if (s.message.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 8),
                child: Text(s.message, style: const TextStyle(fontSize: 12, color: Colors.grey))),
        ]),
      ),
    );
  }

  Widget _row(String k, String v, {Color? color}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
      Text(k, style: const TextStyle(color: Colors.grey)),
      Text(v, style: TextStyle(fontWeight: FontWeight.w600, color: color)),
    ]),
  );
}

class _MiniStat extends StatelessWidget {
  final String label, value;
  const _MiniStat(this.label, this.value);
  @override
  Widget build(BuildContext context) => Expanded(
    child: Card(child: Padding(padding: const EdgeInsets.all(16),
      child: Column(children: [
        Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        Text(label, style: const TextStyle(color: Colors.grey)),
      ]))),
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../data/repos.dart';

final _won = NumberFormat('#,###');
final _hm = DateFormat('MM/dd HH:mm');

Widget _async<T>(AsyncValue<List<T>> v, Widget Function(List<T>) build, String empty) {
  return v.when(
    loading: () => const Center(child: CircularProgressIndicator()),
    error: (e, _) => Center(child: Text('오류: $e')),
    data: (list) => list.isEmpty
        ? Center(child: Text(empty, style: const TextStyle(color: Colors.grey)))
        : build(list),
  );
}

// ── 후보 ──
class CandidatesView extends ConsumerWidget {
  const CandidatesView({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final v = ref.watch(candidatesProvider);
    return _async(v, (list) {
      final sorted = [...list]..sort((a, b) => a.dropRatio.compareTo(b.dropRatio));
      return ListView.separated(
        itemCount: sorted.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (_, i) {
          final c = sorted[i];
          return ListTile(
            dense: true,
            title: Text('${c.name} (${c.code})'),
            subtitle: Text('해제 ${_won.format(c.releaseAmount)} · 현재 ${_won.format(c.currentPrice)} · ${c.status}'),
            trailing: Text('${c.dropRatio > 0 ? '+' : ''}${c.dropRatio}%',
                style: TextStyle(fontWeight: FontWeight.bold,
                    color: c.dropRatio <= 25 ? Colors.orange : Colors.grey)),
          );
        },
      );
    }, '후보 없음');
  }
}

// ── 포지션 ──
class PositionsView extends ConsumerWidget {
  const PositionsView({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final v = ref.watch(positionsProvider);
    return _async(v, (list) => ListView.separated(
      itemCount: list.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final p = list[i];
        final up = p.pnl >= 0;
        return ListTile(
          title: Text('${p.name} (${p.code})'),
          subtitle: Text('${p.qty}주 · 평단 ${_won.format(p.avgPrice)} · 현재 ${_won.format(p.currentPrice)}'),
          trailing: Column(mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text('${up ? '+' : ''}${_won.format(p.pnl)}',
                  style: TextStyle(color: up ? Colors.green : Colors.red, fontWeight: FontWeight.bold)),
              Text('${p.pnlPct.toStringAsFixed(1)}%',
                  style: TextStyle(color: up ? Colors.green : Colors.red, fontSize: 12)),
            ]),
        );
      },
    ), '보유 종목 없음');
  }
}

// ── 주문 ──
class OrdersView extends ConsumerWidget {
  const OrdersView({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final v = ref.watch(ordersProvider);
    return _async(v, (list) => ListView.separated(
      itemCount: list.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final o = list[i];
        final buy = o.side == 'buy';
        return ListTile(
          dense: true,
          leading: Icon(buy ? Icons.arrow_downward : Icons.arrow_upward,
              color: buy ? Colors.red : Colors.blue),
          title: Text('${o.name} · ${buy ? '매수' : '매도'} ${o.qty}주'),
          subtitle: Text('${_won.format(o.price)}원 · ${o.status} · ${o.reason}'),
          trailing: Text(o.createdAt == null ? '' : _hm.format(o.createdAt!),
              style: const TextStyle(fontSize: 11, color: Colors.grey)),
        );
      },
    ), '주문 없음');
  }
}

// ── 이벤트 ──
Color _sev(String s) => switch (s) {
  'critical' => Colors.red, 'high' => Colors.orange, 'warn' => Colors.amber, _ => Colors.grey,
};

class EventsView extends ConsumerWidget {
  const EventsView({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final v = ref.watch(eventsProvider);
    return _async(v, (list) => ListView.separated(
      itemCount: list.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final e = list[i];
        return ListTile(
          dense: true,
          leading: Icon(Icons.circle, size: 12, color: _sev(e.severity)),
          title: Text(e.title),
          subtitle: e.message.isEmpty ? null : Text(e.message),
          trailing: Text(e.createdAt == null ? '' : _hm.format(e.createdAt!),
              style: const TextStyle(fontSize: 11, color: Colors.grey)),
        );
      },
    ), '이벤트 없음');
  }
}

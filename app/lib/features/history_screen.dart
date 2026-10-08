import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../core/net_error.dart';
import '../data/models.dart';
import '../data/repos.dart';

final _won = NumberFormat('#,###');
final _ymd = DateFormat('yy.MM.dd');
final _ymdhm = DateFormat('MM/dd HH:mm');

String exitReasonKr(String r) => switch (r) {
  'limit_up' => '상한가', 'take_profit_partial' => '분할익절', 'post_sell_gain' => '2차상승',
  'trailing_stop' => '트레일링', 'kill' => '긴급정지', 'manual' => '수동', 'external' => '외부/알수없음',
  '' => '-', _ => r,
};

/// 이력 탭 — 거래 사이클(첫 매수 → 전량 매도) 목록. 금액은 키움 체결 실데이터 합계(D-016).
class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final v = ref.watch(tradesProvider);
    return v.when(
      skipError: true,
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => NetErrorView(e, onRetry: () => ref.invalidate(tradesProvider)),
      data: (list) {
        if (list.isEmpty) return const Center(child: Text('거래 이력 없음'));
        final closed = list.where((t) => t.status == 'closed' && t.profit != null).toList();
        final totalProfit = closed.fold<int>(0, (a, t) => a + t.profit!);
        final wins = closed.where((t) => t.profit! > 0).length;
        final avgPct = closed.isEmpty ? 0.0 : closed.fold<double>(0, (a, t) => a + (t.profitPct ?? 0)) / closed.length;
        return ListView(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
          children: [
            _SummaryCard(totalProfit: totalProfit, closedCount: closed.length, wins: wins, avgPct: avgPct,
                openCount: list.length - closed.length),
            const SizedBox(height: 8),
            for (final t in list) _TradeTile(t),
          ],
        );
      },
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final int totalProfit, closedCount, wins, openCount;
  final double avgPct;
  const _SummaryCard({required this.totalProfit, required this.closedCount, required this.wins,
      required this.avgPct, required this.openCount});
  @override
  Widget build(BuildContext context) {
    final up = totalProfit >= 0;
    final winRate = closedCount == 0 ? '-' : '${(wins * 100 / closedCount).toStringAsFixed(0)}%';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('누적 실현 수익금 (수수료·세금 차감)', style: TextStyle(color: Colors.grey, fontSize: 12)),
          Text('${up ? '+' : ''}${_won.format(totalProfit)} 원',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: up ? Colors.green : Colors.red)),
          const SizedBox(height: 8),
          Row(children: [
            _stat('청산 완료', '$closedCount건'),
            _stat('보유중', '$openCount건'),
            _stat('승률', winRate),
            _stat('평균 수익률', closedCount == 0 ? '-' : '${avgPct.toStringAsFixed(1)}%'),
          ]),
        ]),
      ),
    );
  }

  Widget _stat(String k, String v) => Expanded(child: Column(children: [
    Text(v, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
    Text(k, style: const TextStyle(color: Colors.grey, fontSize: 11)),
  ]));
}

class _TradeTile extends StatelessWidget {
  final Trade t;
  const _TradeTile(this.t);

  @override
  Widget build(BuildContext context) {
    final closed = t.status == 'closed';
    final up = (t.profit ?? 0) >= 0;
    final color = closed ? (up ? Colors.green : Colors.red) : Colors.grey;
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: InkWell(
        onTap: () => _showDetail(context, t),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('${t.name}  ',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold))),
              if (!closed) _badge('보유중', Colors.blueGrey)
              else _badge(exitReasonKr(t.exitReason), Colors.indigo),
            ]),
            const SizedBox(height: 6),
            _kv('최초 매수일', _ymd.format(t.firstBuyAt)),
            _kv('최종 매도일', closed && t.lastSellAt != null ? _ymd.format(t.lastSellAt!) : ''),
            _kv('총 매수금액', '${_won.format(t.buyAmount)} 원'),
            _kv('최종 수익률', closed && t.profitPct != null ? '${t.profitPct! >= 0 ? '+' : ''}${t.profitPct!.toStringAsFixed(2)}%' : '',
                color: color),
            _kv('최종 수익금', closed && t.profit != null ? '${up ? '+' : ''}${_won.format(t.profit)} 원' : '',
                color: color, bold: true),
          ]),
        ),
      ),
    );
  }

  Widget _badge(String s, Color c) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    decoration: BoxDecoration(color: c.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(10)),
    child: Text(s, style: TextStyle(fontSize: 11, color: c)),
  );

  Widget _kv(String k, String v, {Color? color, bool bold = false}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 1),
    child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
      Text(k, style: const TextStyle(color: Colors.grey, fontSize: 13)),
      Text(v, style: TextStyle(fontSize: 13, color: color, fontWeight: bold ? FontWeight.bold : null)),
    ]),
  );
}

void _showDetail(BuildContext context, Trade t) {
  final closed = t.status == 'closed';
  final avgBuy = t.buyQty > 0 ? t.buyAmount / t.buyQty : 0;
  final avgSell = t.sellQty > 0 ? t.sellAmount / t.sellQty : 0;
  Widget row(String k, String v) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
      Text(k, style: const TextStyle(color: Colors.grey)), Text(v, style: const TextStyle(fontWeight: FontWeight.w600)),
    ]),
  );
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) => DraggableScrollableSheet(
      expand: false, initialChildSize: 0.7, maxChildSize: 0.95,
      builder: (_, sc) => ListView(
        controller: sc,
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        children: [
          Row(children: [
            Expanded(child: Text('${t.name} (${t.code})', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold))),
            IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.of(ctx).pop()),
          ]),
          row('상태', closed ? '청산 완료 · ${exitReasonKr(t.exitReason)}' : '보유중'),
          row('최초 매수', _ymdhm.format(t.firstBuyAt)),
          row('최종 매도', closed && t.lastSellAt != null ? _ymdhm.format(t.lastSellAt!) : '-'),
          row('보유 일수', closed && t.holdingDays != null ? '${t.holdingDays}일' : '-'),
          const Divider(height: 20),
          row('매수', '${t.buyCount}회 · ${_won.format(t.buyQty)}주 · 평균 ${_won.format(avgBuy.round())}원'),
          row('총 매수금액', '${_won.format(t.buyAmount)} 원'),
          row('매도', '${t.sellCount}회 · ${_won.format(t.sellQty)}주 · 평균 ${_won.format(avgSell.round())}원'),
          row('총 매도금액', '${_won.format(t.sellAmount)} 원'),
          row('수수료 + 세금', '${_won.format(t.commission + t.tax)} 원 (수수료 ${_won.format(t.commission)} · 세금 ${_won.format(t.tax)})'),
          row('최종 수익금', closed && t.profit != null ? '${t.profit! >= 0 ? '+' : ''}${_won.format(t.profit)} 원' : '-'),
          row('최종 수익률', closed && t.profitPct != null ? '${t.profitPct!.toStringAsFixed(2)}%' : '-'),
          const Divider(height: 20),
          const Text('체결 주문', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          if (t.orders.isEmpty) const Text('-', style: TextStyle(color: Colors.grey)),
          for (final o in t.orders)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '${o['at'] != null ? _ymdhm.format(DateTime.tryParse('${o['at']}')?.toLocal() ?? t.firstBuyAt) : ''}  '
                '${o['side'] == 'sell' ? '매도' : '매수'} ${_won.format(o['qty'] ?? 0)}주 @ ${_won.format(o['price'] ?? 0)}'
                '${(o['reason'] ?? '').toString().isNotEmpty ? ' · ${exitReasonKr('${o['reason']}') == o['reason'] ? o['reason'] : exitReasonKr('${o['reason']}')}' : ''}',
                style: const TextStyle(fontSize: 13),
              ),
            ),
        ],
      ),
    ),
  );
}

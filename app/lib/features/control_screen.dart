import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/repos.dart';
import 'dashboard_screen.dart' show statusColor;

class ControlScreen extends ConsumerWidget {
  const ControlScreen({super.key});

  Future<void> _send(BuildContext context, String type, {Map<String, dynamic>? payload}) async {
    try {
      await sendCommand(type, payload: payload);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text("'$type' 명령 전송됨 (봇 처리 대기)")));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('명령 실패: $e'), backgroundColor: Colors.red));
      }
    }
  }

  Future<void> _confirmKill(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('⚠ 긴급 정지'),
        content: const Text('보유 종목을 전량 시장가 청산하고 봇을 정지합니다.\n계속하시겠습니까?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('취소')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(c, true),
            child: const Text('전량청산+정지')),
        ],
      ),
    );
    if (ok == true && context.mounted) await _send(context, 'kill');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botStateProvider);
    final status = bot.maybeWhen(data: (b) => b?.status ?? 'unknown', orElse: () => '…');

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Row(children: [
          const Text('현재 상태', style: TextStyle(color: Colors.grey)),
          const Spacer(),
          Container(width: 10, height: 10, decoration: BoxDecoration(
              color: statusColor(status), shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(status.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.bold)),
        ]))),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: FilledButton.icon(
            onPressed: () => _send(context, 'start'),
            icon: const Icon(Icons.play_arrow), label: const Text('시작'))),
          const SizedBox(width: 12),
          Expanded(child: FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Colors.blueGrey),
            onPressed: () => _send(context, 'stop'),
            icon: const Icon(Icons.stop), label: const Text('정지'))),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: OutlinedButton.icon(
            onPressed: () => _send(context, 'pause'),
            icon: const Icon(Icons.pause), label: const Text('일시정지'))),
          const SizedBox(width: 12),
          Expanded(child: OutlinedButton.icon(
            onPressed: () => _send(context, 'resume'),
            icon: const Icon(Icons.replay), label: const Text('재개'))),
        ]),
        const SizedBox(height: 32),
        SizedBox(height: 64, child: FilledButton.icon(
          style: FilledButton.styleFrom(backgroundColor: Colors.red),
          onPressed: () => _confirmKill(context),
          icon: const Icon(Icons.warning_amber, size: 28),
          label: const Text('긴급 정지 (전량청산)',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)))),
        const SizedBox(height: 8),
        const Text('긴급 정지는 2단계 확인 후 실행됩니다.',
            style: TextStyle(fontSize: 12, color: Colors.grey), textAlign: TextAlign.center),
      ],
    );
  }
}

import 'package:flutter/material.dart';

/// 네트워크성 오류 판별(폰 DNS 실패·연결 끊김·타임아웃 등). 2026-10-08
bool isNetworkError(Object e) {
  final s = '$e';
  return s.contains('SocketException') || s.contains('Failed host lookup') ||
      s.contains('ClientException') || s.contains('TimeoutException') ||
      s.contains('Connection closed') || s.contains('Connection reset') ||
      s.contains('Network is unreachable') || s.contains('RealtimeSubscribeException');
}

/// 오류 표시 — 네트워크 오류는 "연결 대기 중(자동 재시도)", 그 외는 원인 요약. 재시도 버튼 선택.
class NetErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;
  final bool compact;
  const NetErrorView(this.error, {super.key, this.onRetry, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final net = isNetworkError(error);
    final title = net ? '네트워크 연결 대기 중…' : '데이터 조회 오류';
    final sub = net ? '연결되면 자동으로 다시 불러옵니다' : '$error';
    final body = Column(mainAxisSize: MainAxisSize.min, children: [
      Icon(net ? Icons.wifi_off : Icons.error_outline, color: Colors.orange, size: compact ? 22 : 36),
      const SizedBox(height: 6),
      Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
      const SizedBox(height: 2),
      Text(sub, textAlign: TextAlign.center, maxLines: 3, overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Colors.grey, fontSize: 12)),
      if (onRetry != null) ...[
        const SizedBox(height: 6),
        TextButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh, size: 18), label: const Text('지금 다시 시도')),
      ],
    ]);
    return compact
        ? Card(child: Padding(padding: const EdgeInsets.all(16), child: Center(child: body)))
        : Center(child: Padding(padding: const EdgeInsets.all(24), child: body));
  }
}

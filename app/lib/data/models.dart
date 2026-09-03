// Supabase 행 → Dart 모델. docs/02 테이블과 매핑.

int _i(dynamic v) => v == null ? 0 : (v is int ? v : int.tryParse('$v') ?? (v as num).toInt());
num _n(dynamic v) => v == null ? 0 : (v is num ? v : num.tryParse('$v') ?? 0);
String _s(dynamic v) => v?.toString() ?? '';

class BotState {
  final String status;
  final bool marketOpen;
  final int equity, cash, dayPnl, positionsCnt;
  final String message;
  final DateTime? heartbeatAt;
  BotState({required this.status, required this.marketOpen, required this.equity,
    required this.cash, required this.dayPnl, required this.positionsCnt,
    required this.message, this.heartbeatAt});

  factory BotState.fromMap(Map<String, dynamic> m) => BotState(
    status: _s(m['status']).isEmpty ? 'unknown' : _s(m['status']),
    marketOpen: m['market_open'] == true,
    equity: _i(m['equity']), cash: _i(m['cash']), dayPnl: _i(m['day_pnl']),
    positionsCnt: _i(m['positions_cnt']), message: _s(m['message']),
    heartbeatAt: DateTime.tryParse(_s(m['heartbeat_at']))?.toLocal(),
  );
}

class Candidate {
  final String code, name, status, signal;
  final int releaseAmount, currentPrice;
  final num dropRatio;
  final DateTime? releaseDate;
  Candidate({required this.code, required this.name, required this.status,
    required this.signal, required this.releaseAmount, required this.currentPrice,
    required this.dropRatio, this.releaseDate});
  factory Candidate.fromMap(Map<String, dynamic> m) => Candidate(
    code: _s(m['code']), name: _s(m['name']), status: _s(m['status']),
    signal: _s(m['signal']), releaseAmount: _i(m['release_amount']),
    currentPrice: _i(m['current_price']), dropRatio: _n(m['drop_ratio']),
    releaseDate: DateTime.tryParse(_s(m['release_date'])),
  );
}

class Position {
  final String code, name;
  final int qty, avgPrice, currentPrice, pnl;
  final num pnlPct;
  Position({required this.code, required this.name, required this.qty,
    required this.avgPrice, required this.currentPrice, required this.pnl,
    required this.pnlPct});
  factory Position.fromMap(Map<String, dynamic> m) => Position(
    code: _s(m['code']), name: _s(m['name']), qty: _i(m['qty']),
    avgPrice: _i(m['avg_price']), currentPrice: _i(m['current_price']),
    pnl: _i(m['pnl']), pnlPct: _n(m['pnl_pct']),
  );
}

class OrderRow {
  final String id, code, name, side, orderType, status, reason;
  final int qty, price;
  final DateTime? createdAt;
  OrderRow({required this.id, required this.code, required this.name,
    required this.side, required this.orderType, required this.status,
    required this.reason, required this.qty, required this.price, this.createdAt});
  factory OrderRow.fromMap(Map<String, dynamic> m) => OrderRow(
    id: _s(m['id']), code: _s(m['code']), name: _s(m['name']), side: _s(m['side']),
    orderType: _s(m['order_type']), status: _s(m['status']), reason: _s(m['reason']),
    qty: _i(m['qty']), price: _i(m['price']),
    createdAt: DateTime.tryParse(_s(m['created_at']))?.toLocal(),
  );
}

class EventRow {
  final String id, type, severity, title, message;
  final DateTime? createdAt;
  EventRow({required this.id, required this.type, required this.severity,
    required this.title, required this.message, this.createdAt});
  factory EventRow.fromMap(Map<String, dynamic> m) => EventRow(
    id: _s(m['id']), type: _s(m['type']), severity: _s(m['severity']),
    title: _s(m['title']), message: _s(m['message']),
    createdAt: DateTime.tryParse(_s(m['created_at']))?.toLocal(),
  );
}

class Settings {
  final bool enabled;
  final String mode;
  final Map<String, dynamic> extra;
  Settings({required this.enabled, required this.mode, required this.extra});
  factory Settings.fromMap(Map<String, dynamic> m) => Settings(
    enabled: m['enabled'] == true, mode: _s(m['mode']).isEmpty ? 'demo' : _s(m['mode']),
    extra: (m['extra'] is Map) ? Map<String, dynamic>.from(m['extra']) : {},
  );
}

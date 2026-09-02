import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/models.dart';
import '../data/repos.dart';

// (그룹, key, 라벨, 정수여부, 기본값) — docs/03 §6. 전부 조절 가능.
const _specs = <(String, String, String, bool, num)>[
  // 기본 설정
  ('기본 설정', 'min_price', '최소 매수가(원)', true, 1000),
  ('기본 설정', 'max_positions', '최대 보유종목수', true, 5),
  ('기본 설정', 'max_unrealized_loss_krw', '평가손실 매수중단 한도(원) — 보유 평가손실이 이만큼이면 신규매수 중단', true, 500000),
  ('기본 설정', 'tick_seconds', '평가 주기(초)', true, 5),
  // 매수 설정
  ('매수 설정', 'entry_drop_pct', '진입 하락비율 기준(%) — 해제가 대비 이 % 이상 하락 시 매수', false, 30),
  ('매수 설정', 'per_stock_krw', '종목당 총 투자액(원)', true, 1000000),
  ('매수 설정', 'entry_split_pct', '1회 매수 비중 (0~1, 0.3=30%)', false, 0.30),
  ('매수 설정', 'max_entries', '최대 분할매수 횟수', true, 4),
  ('매수 설정', 'add_on_drop_pct', '추가매수 하락 기준 (0~1, 0.07=7%)', false, 0.07),
  // 매도 설정
  ('매도 설정', 'take_profit_pct', '분할익절 수익률(%)', false, 15),
  ('매도 설정', 'first_sell_portion', '첫 분할매도 비중 (0~1, 0.5=50%)', false, 0.50),
  ('매도 설정', 'post_sell_stop_pct', '분할매도후 하락 전량 (0~1, 0.05=5%)', false, 0.05),
  ('매도 설정', 'limit_up_pct', '급등 전량매도 기준(%) (예 29≈상한가)', false, 29),
  // Envelope 지표
  ('Envelope 지표', 'env_period', 'Envelope 기간(일)', true, 20),
  ('Envelope 지표', 'env_band', 'Envelope 밴드 (0~1, 0.1=±10%)', false, 0.10),
];

// 그룹 순서 (등장 순서 유지)
List<String> get _groups {
  final seen = <String>[];
  for (final s in _specs) {
    if (!seen.contains(s.$1)) seen.add(s.$1);
  }
  return seen;
}

const _groupIcon = <String, IconData>{
  '기본 설정': Icons.settings,
  '매수 설정': Icons.arrow_downward,
  '매도 설정': Icons.arrow_upward,
  'Envelope 지표': Icons.show_chart,
};

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});
  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _ctrls = <String, TextEditingController>{};
  bool _enabled = false;
  bool _initialized = false;
  bool _saving = false;

  void _initFrom(Settings s) {
    _enabled = s.enabled;
    for (final (_, key, _, _, def) in _specs) {
      final v = s.extra[key] ?? def;
      _ctrls[key] = TextEditingController(text: '$v');
    }
    _initialized = true;
  }

  @override
  void dispose() {
    for (final c in _ctrls.values) { c.dispose(); }
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final extra = <String, dynamic>{};
    for (final (_, key, _, isInt, def) in _specs) {
      final t = _ctrls[key]!.text.trim();
      extra[key] = isInt ? (int.tryParse(t) ?? def.toInt()) : (double.tryParse(t) ?? def.toDouble());
    }
    try {
      await saveSettings(enabled: _enabled, extra: extra);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('설정 저장됨 (봇에 반영)')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('저장 실패: $e'), backgroundColor: Colors.red));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(String key, String label, bool isInt) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextField(
      controller: _ctrls[key],
      keyboardType: TextInputType.numberWithOptions(decimal: !isInt),
      decoration: InputDecoration(
          labelText: label, border: const OutlineInputBorder(), isDense: true),
    ),
  );

  Widget _groupCard(String group) {
    final fields = _specs.where((s) => s.$1 == group);
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(_groupIcon[group] ?? Icons.tune, size: 20, color: Colors.indigo.shade200),
            const SizedBox(width: 8),
            Text(group, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ]),
          const Divider(),
          for (final (_, key, label, isInt, _) in fields) _field(key, label, isInt),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsProvider);
    return settings.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('설정 조회 오류: $e', textAlign: TextAlign.center))),
      data: (s) {
        if (s != null && !_initialized) _initFrom(s);
        if (!_initialized) return const Center(child: Text('설정 없음'));
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              color: _enabled ? Colors.green.shade900.withValues(alpha: 0.3) : null,
              child: SwitchListTile(
                title: const Text('자동매매 활성화',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text(_enabled ? '조건 충족 시 자동 매수/매도' : '분석·모니터링만 (매매 안 함)'),
                value: _enabled,
                onChanged: (v) => setState(() => _enabled = v),
              ),
            ),
            const SizedBox(height: 16),
            for (final g in _groups) _groupCard(g),
            SizedBox(height: 50, child: FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: const Icon(Icons.save),
              label: Text(_saving ? '저장 중…' : '설정 저장'))),
            const SizedBox(height: 24),
          ],
        );
      },
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/models.dart';
import '../data/repos.dart';

// (key, 라벨, 정수여부, 기본값) — docs/03 §6. 전부 조절 가능.
const _specs = <(String, String, bool, num)>[
  ('min_price', '최소 매수가(원)', true, 1000),
  ('entry_drop_min', '진입 하락비율 하한(%)', false, 30),
  ('entry_drop_max', '진입 하락비율 상한(%)', false, 40),
  ('per_stock_krw', '종목당 총 투자액(원)', true, 1000000),
  ('entry_split_pct', '1회 매수 비중(0~1)', false, 0.30),
  ('max_entries', '최대 분할매수 횟수', true, 4),
  ('add_on_drop_pct', '추가매수 하락 기준(0~1)', false, 0.07),
  ('max_positions', '최대 보유종목수', true, 5),
  ('env_period', 'Envelope 기간(일)', true, 20),
  ('env_band', 'Envelope 밴드(0~1)', false, 0.10),
  ('take_profit_pct', '분할익절 수익률(%)', false, 15),
  ('first_sell_portion', '첫 분할매도 비중(0~1)', false, 0.50),
  ('post_sell_stop_pct', '분할매도후 하락 전량(0~1)', false, 0.05),
  ('daily_max_loss_krw', '일 손실 상한(원)', true, 500000),
  ('tick_seconds', '평가 주기(초)', true, 5),
];

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
    for (final (key, _, _, def) in _specs) {
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
    for (final (key, _, isInt, def) in _specs) {
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

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsProvider);
    return settings.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('설정 조회 오류: $e')),
      data: (s) {
        if (s != null && !_initialized) _initFrom(s);
        if (!_initialized) return const Center(child: Text('설정 없음'));
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SwitchListTile(
              title: const Text('자동매매 활성화 (enabled)'),
              subtitle: const Text('끄면 분석·모니터링만, 켜면 조건 충족 시 매수/매도'),
              value: _enabled,
              onChanged: (v) => setState(() => _enabled = v),
            ),
            const Divider(),
            for (final (key, label, isInt, _) in _specs)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: TextField(
                  controller: _ctrls[key],
                  keyboardType: TextInputType.numberWithOptions(decimal: !isInt),
                  decoration: InputDecoration(
                      labelText: label, border: const OutlineInputBorder(),
                      isDense: true),
                ),
              ),
            const SizedBox(height: 20),
            SizedBox(height: 48, child: FilledButton.icon(
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

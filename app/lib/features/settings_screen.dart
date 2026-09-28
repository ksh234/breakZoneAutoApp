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
  ('기본 설정', 'unfilled_cancel_min', '미체결 취소 지속시간(분) — 아래 괴리 상태가 이 시간 이상 지속되면 취소(매수·매도), 0=안 함', true, 10),
  ('기본 설정', 'unfilled_cancel_dev_pct', '미체결 취소 괴리율(%) — 현재가가 주문가에서 이 % 이상 벗어난 상태 기준. 0=괴리 무관(접수 후 시간만)', false, 1.0),
  // 매수 설정
  ('매수 설정', 'entry_drop_pct', '진입 하락비율 기준(%) — 해제가 대비 이 % 이상 하락해야 매수구간', false, 30),
  ('매수 설정', 'entry_rebound_pct', '저가 반등 매수(%) — 매수구간 저점서 이 % 오르면 매수. 신규·추가매수 공통. 0=즉시', false, 0.0),
  ('매수 설정', 'per_stock_krw', '종목당 총 투자액(원)', true, 1000000),
  ('매수 설정', 'entry_split_pct', '1회 매수 비중(%) — 종목당 총 투자액 대비', false, 30.0),
  ('매수 설정', 'max_entries', '최대 분할매수 횟수', true, 4),
  ('매수 설정', 'add_on_drop_pct', '추가매수 하락 기준(%) — 직전 매수가 대비 이 % 하락 시 물타기', false, 7.0),
  // 매도 설정
  ('매도 설정', 'take_profit_pct', '분할익절 수익률(%)', false, 15),
  ('매도 설정', 'first_sell_portion', '첫 분할매도 비중(%) — 분할익절 때 파는 비율', false, 50.0),
  ('매도 설정', 'post_sell_stop_pct', '분할매도후 하락 전량(%) — 고점 대비 이 % 하락 시 잔량 전량', false, 5.0),
  ('매도 설정', 'post_sell_gain_pct', '2차 상승 전량매도(%) — 1차 매도가 대비 이만큼 오르면 잔량 전량 (0=끔)', false, 0),
  ('매도 설정', 'limit_up_pct', '급등 전량매도 기준(%) (예 29≈상한가)', false, 29),
  // Envelope 지표
  ('Envelope 지표', 'env_period', 'Envelope 기간(일)', true, 20),
  ('Envelope 지표', 'env_band', 'Envelope 밴드(%) — 이동평균 대비 ±폭', false, 10.0),
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

  // 단위 통일(2026-09-28): 모든 비율 항목은 %(소수 1자리). 옛 저장값(params_version<2)은 0~1 비율 → ×100 표시.
  static const _ratioLegacyKeys = {'env_band', 'entry_rebound_pct', 'entry_split_pct',
                                   'add_on_drop_pct', 'first_sell_portion', 'post_sell_stop_pct'};
  static const _paramsVersion = 2;

  void _initFrom(Settings s) {
    _enabled = s.enabled;
    final legacy = (s.extra['params_version'] ?? 1) < _paramsVersion;
    for (final (_, key, _, isInt, def) in _specs) {
      num v = (s.extra[key] as num?) ?? def;
      if (legacy && _ratioLegacyKeys.contains(key)) v = (v * 100 * 10).round() / 10;
      _ctrls[key] = TextEditingController(text: isInt ? '${v.toInt()}' : v.toStringAsFixed(1));
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
      extra[key] = isInt
          ? (int.tryParse(t) ?? def.toInt())
          : (((double.tryParse(t) ?? def.toDouble()) * 10).round() / 10);   // 소수 1자리
    }
    extra['params_version'] = _paramsVersion;
    try {
      await saveSettings(enabled: _enabled, extra: extra);
      // 봇에 즉시 반영 요청(명령). 명령이 유실돼도 봇이 30초 주기로 settings 재로드함.
      await sendCommand('set_param');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('설정 저장됨 — 봇에 반영 요청(이벤트 탭에서 "설정 반영" 확인)')));
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
                subtitle: Text(_enabled
                    ? '조건 충족 시 자동 매수 + 보유 청산'
                    : '신규 매수 중단 (보유 종목 청산 규칙은 계속 작동)'),
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

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/models.dart';
import '../data/repos.dart';

// (그룹, key, 항목명, 설명(ⓘ 레이어), 정수여부, 기본값) — docs/03 §6. 전부 조절 가능. 단위: 비율은 전부 %(소수 1자리).
const _specs = <(String, String, String, String, bool, num)>[
  // 기본 설정
  ('기본 설정', 'min_price', '최소 매수가(원)',
      '현재가가 이 금액 미만인 종목은 매수하지 않습니다(저가주 제외). 신규·추가매수 공통. 0이면 제한 없음.', true, 1000),
  ('기본 설정', 'max_positions', '최대 보유종목수',
      '동시에 보유할 수 있는 종목 수 상한입니다. 이 수에 도달하면 신규 진입을 하지 않습니다(추가매수는 가능).', true, 5),
  ('기본 설정', 'max_unrealized_loss_krw', '평가손실 매수중단 한도(원)',
      '보유 종목 전체의 평가손실(미실현)이 이 금액 이상이면 신규·추가매수를 중단합니다. 청산(매도) 규칙은 계속 작동합니다. 하락장에서 물타기가 늘어나는 것을 막는 안전장치입니다.', true, 500000),
  ('기본 설정', 'tick_seconds', '평가 주기(초)',
      '봇이 매수·매도 조건을 판정하는 주기입니다. 짧을수록 반응이 빠르지만 키움 API 호출이 늘어납니다. 5초 권장.', true, 5),
  ('기본 설정', 'unfilled_cancel_min', '미체결 취소 지속시간(분)',
      '아래 "미체결 취소 괴리율" 조건이 이 시간 이상 연속으로 이어지면 미체결 주문(매수·매도)을 취소합니다. 취소 후 다음 판정에서 조건이 맞으면 현재가로 다시 주문합니다. 0이면 취소하지 않습니다.', true, 10),
  ('기본 설정', 'unfilled_cancel_dev_pct', '미체결 취소 괴리율(%)',
      '현재가가 주문가에서 이 % 이상 벗어난 상태를 "괴리"로 봅니다. 현재가가 주문가에 붙어 있으면(예: 상한가 대기) 취소하지 않아 대기열을 지킵니다. 0이면 괴리와 무관하게 접수 후 경과시간만으로 취소합니다.', false, 1.0),
  // 매수 설정
  ('매수 설정', 'entry_drop_pct', '진입 하락비율 기준(%)',
      '현재가가 경고 해제금액보다 이 % 이상 낮아야 매수구간으로 봅니다. 상한은 없습니다(더 많이 떨어질수록 대상).', false, 30),
  ('매수 설정', 'entry_rebound_pct', '저가 반등 매수(%)',
      '매수구간에 들어온 뒤 기록된 저점 대비 이 % 이상 반등해야 매수합니다(급락 중 매수 방지). 신규·추가매수 공통. 저점은 매수구간을 벗어나면 초기화됩니다. 0이면 반등을 보지 않고 즉시 매수합니다.', false, 0.0),
  ('매수 설정', 'per_stock_krw', '종목당 총 투자액(원)',
      '한 종목에 누적으로 넣을 수 있는 매수금액 상한입니다. 분할매수 합계가 이 금액을 넘지 않습니다.', true, 1000000),
  ('매수 설정', 'entry_split_pct', '1회 매수 비중(%)',
      '종목당 총 투자액 대비 한 번에 매수하는 비율입니다. 예: 총액 100만·30% → 1회 30만원.', false, 30.0),
  ('매수 설정', 'max_entries', '최대 분할매수 횟수',
      '신규 진입과 추가매수(물타기)를 합한 최대 매수 횟수입니다. 이 횟수 또는 총 투자액에 먼저 도달하면 더 사지 않습니다.', true, 4),
  ('매수 설정', 'add_on_drop_pct', '추가매수 하락 기준(%)',
      '직전 매수가 대비 이 % 이상 하락하면 1회분을 추가매수(물타기)합니다. 평단가가 아니라 직전 매수가 기준이라 기준선이 매수마다 계단식으로 내려갑니다. 저가 반등 조건이 켜져 있으면 추매에도 적용됩니다.', false, 7.0),
  // 매도 설정
  ('매도 설정', 'take_profit_pct', '분할익절 수익률(%)',
      '평단가 대비 수익률이 이 % 이상이면 첫 분할매도(익절)를 시작합니다. 종목당 한 번만 일어나며, 이후 잔량은 트레일링·2차 상승·급등 규칙으로 정리됩니다.', false, 15),
  ('매도 설정', 'first_sell_portion', '첫 분할매도 비중(%)',
      '분할익절 때 보유수량 중 파는 비율입니다. 예: 50 → 절반 매도.', false, 50.0),
  ('매도 설정', 'post_sell_stop_pct', '분할매도후 하락 전량(%)',
      '분할매도 이후 기록된 고점 대비 이 % 이상 떨어지면 잔량을 전량 매도합니다(트레일링 스톱).', false, 5.0),
  ('매도 설정', 'post_sell_gain_pct', '2차 상승 전량매도(%)',
      '분할매도 이후 1차 매도가 대비 이 % 이상 오르면 잔량을 전량 매도합니다(평단가 아님). 급등 규칙과 별개로 목표 상승률에서 확정합니다. 0이면 사용하지 않습니다.', false, 0),
  ('매도 설정', 'limit_up_pct', '급등 전량매도 기준(%)',
      '전일 종가 대비 이 % 이상 오르면(예: 29 ≈ 상한가) 분할매도 여부와 관계없이 보유 전량을 매도합니다. 청산 규칙 중 최우선입니다.', false, 29),
  // Envelope 지표
  ('Envelope 지표', 'env_period', 'Envelope 기간(일)',
      'Envelope 계산에 쓰는 이동평균 기간(거래일)입니다. 어제까지의 종가로 계산합니다.', true, 20),
  ('Envelope 지표', 'env_band', 'Envelope 밴드(%)',
      '이동평균 대비 ±폭입니다. 신규 진입은 현재가가 하단(이동평균 − 밴드%) 아래일 때만 합니다. 매도에는 쓰지 않습니다.', false, 10.0),
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
    for (final (_, key, _, _, isInt, def) in _specs) {
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
    for (final (_, key, _, _, isInt, def) in _specs) {
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

  void _showHelp(String label, String help) => showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      titlePadding: const EdgeInsets.fromLTRB(20, 12, 8, 0),
      title: Row(children: [
        Expanded(child: Text(label, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold))),
        IconButton(icon: const Icon(Icons.close), tooltip: '닫기', onPressed: () => Navigator.of(ctx).pop()),
      ]),
      content: Text(help, style: const TextStyle(height: 1.5)),
    ),
  );

  Widget _field(String key, String label, String help, bool isInt) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextField(
      controller: _ctrls[key],
      keyboardType: TextInputType.numberWithOptions(decimal: !isInt),
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        isDense: true,
        suffixIcon: IconButton(
          icon: const Icon(Icons.help_outline),
          tooltip: '설명',
          onPressed: () => _showHelp(label, help),
        ),
      ),
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
          for (final (_, key, label, help, isInt, _) in fields) _field(key, label, help, isInt),
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

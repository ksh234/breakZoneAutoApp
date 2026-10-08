import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'data/repos.dart';
import 'core/supabase.dart';
import 'features/dashboard_screen.dart';
import 'features/control_screen.dart';
import 'features/settings_screen.dart';
import 'features/lists.dart';
import 'features/history_screen.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> with WidgetsBindingObserver {
  int _i = 0;
  DateTime? _pausedAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // 백그라운드에서 10초 이상 있다가 돌아오면 전체 데이터 다시 구독(안드로이드가 네트워크를 끊어둔 경우 회복). 2026-10-08
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden) {
      _pausedAt ??= DateTime.now();
    } else if (state == AppLifecycleState.resumed) {
      final away = _pausedAt == null ? Duration.zero : DateTime.now().difference(_pausedAt!);
      _pausedAt = null;
      if (away.inSeconds >= 10) refreshAllStreams(ref);
    }
  }

  static const _items = <(String, IconData, Widget)>[
    ('대시보드', Icons.dashboard, DashboardScreen()),
    ('후보', Icons.list_alt, CandidatesView()),
    ('포지션', Icons.account_balance_wallet, PositionsView()),
    ('주문', Icons.receipt_long, OrdersView()),
    ('이력', Icons.history, HistoryScreen()),
    ('이벤트', Icons.notifications, EventsView()),
    ('제어', Icons.tune, ControlScreen()),
    ('설정', Icons.settings, SettingsScreen()),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_items[_i].$1),
        actions: [
          IconButton(
            tooltip: '로그아웃',
            icon: const Icon(Icons.logout),
            onPressed: () => supabase.auth.signOut(),
          ),
        ],
      ),
      drawer: Drawer(
        child: ListView(
          children: [
            const DrawerHeader(
              decoration: BoxDecoration(color: Colors.indigo),
              child: Align(alignment: Alignment.bottomLeft,
                child: Text('breakZone 자동매매',
                    style: TextStyle(color: Colors.white, fontSize: 18))),
            ),
            for (var k = 0; k < _items.length; k++)
              ListTile(
                leading: Icon(_items[k].$2),
                title: Text(_items[k].$1),
                selected: k == _i,
                onTap: () {
                  setState(() => _i = k);
                  Navigator.pop(context);
                },
              ),
          ],
        ),
      ),
      body: IndexedStack(index: _i, children: [for (final it in _items) it.$3]),
    );
  }
}

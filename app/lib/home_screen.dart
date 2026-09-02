import 'package:flutter/material.dart';
import 'core/supabase.dart';
import 'features/dashboard_screen.dart';
import 'features/control_screen.dart';
import 'features/settings_screen.dart';
import 'features/lists.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _i = 0;

  static const _items = <(String, IconData, Widget)>[
    ('대시보드', Icons.dashboard, DashboardScreen()),
    ('후보', Icons.list_alt, CandidatesView()),
    ('포지션', Icons.account_balance_wallet, PositionsView()),
    ('주문', Icons.receipt_long, OrdersView()),
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

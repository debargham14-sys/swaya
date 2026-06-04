import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/measurement_result.dart';
import '../screens/camera_screen.dart';
import '../screens/capture_guide_screen.dart';
import '../screens/chat_screen.dart';
import '../screens/height_screen.dart';
import '../screens/history_screen.dart';
import '../screens/home_screen.dart';
import '../screens/onboarding_screen.dart';
import '../screens/processing_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/results_screen.dart';
import '../screens/review_screen.dart';
import '../screens/welcome_screen.dart';
import '../widgets/app_shell.dart';

final rootNavigatorKey = GlobalKey<NavigatorState>();

GoRouter createAppRouter() {
  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const WelcomeScreen(),
      ),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return AppShell(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/history',
                builder: (context, state) => const HistoryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/assistant',
                builder: (context, state) => const ChatScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const ProfileScreen(),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        path: '/scan/height',
        builder: (context, state) => const HeightScreen(),
      ),
      GoRoute(
        path: '/scan/guide',
        builder: (context, state) => const CaptureGuideScreen(),
      ),
      GoRoute(
        path: '/scan/capture/:view',
        builder: (context, state) {
          final view = CaptureView.values.byName(state.pathParameters['view']!);
          return CameraScreen(view: view);
        },
      ),
      GoRoute(
        path: '/scan/review',
        builder: (context, state) => const ReviewScreen(),
      ),
      GoRoute(
        path: '/scan/processing',
        builder: (context, state) => const ProcessingScreen(),
      ),
      GoRoute(
        path: '/scan/results',
        builder: (context, state) => const ResultsScreen(),
      ),
      GoRoute(
        path: '/scan/assistant',
        builder: (context, state) => const ChatScreen(),
      ),
    ],
  );
}

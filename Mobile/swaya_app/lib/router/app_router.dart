import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/blouse_measurements.dart';
import '../models/measurement_result.dart';
import '../providers/auth_controller.dart';
import '../screens/auth/login_screen.dart';
import '../screens/auth/register_screen.dart';
import '../screens/auth/reset_password_screen.dart';
import '../screens/app/add_measurements_screen.dart';
import '../screens/app/avatar_screen.dart';
import '../screens/app/capture_images_screen.dart';
import '../screens/app/create_persona_screen.dart';
import '../screens/app/home_v2_screen.dart';
import '../screens/app/manual_entry_screen.dart';
import '../screens/app/orders_screen.dart';
import '../screens/app/persona_detail_screen.dart';
import '../screens/app/persona_saved_screen.dart';
import '../models/persona.dart';
import '../screens/app/profile_v2_screen.dart';
import '../screens/app/review_measurements_screen.dart';
import '../screens/camera_screen.dart';
import '../screens/capture_guide_screen.dart';
import '../screens/chat_screen.dart';
import '../screens/height_screen.dart';
import '../screens/history_screen.dart';
import '../screens/scan_detail_screen.dart';
import '../models/scan_record.dart';
import '../screens/home_screen.dart';
import '../screens/onboarding_screen.dart';
import '../screens/processing_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/results_screen.dart';
import '../screens/review_screen.dart';
import '../screens/vest_result_screen.dart';
import '../screens/vest_scan_screen.dart';
import '../screens/welcome_screen.dart';
import '../models/vest_measurement.dart';
import '../widgets/app_shell.dart';

final rootNavigatorKey = GlobalKey<NavigatorState>();

/// Public routes reachable while signed out. Everything else requires auth.
const _authRoutes = {'/auth', '/auth/register', '/auth/reset'};

GoRouter createAppRouter(AuthController auth) {
  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/',
    refreshListenable: auth,
    redirect: (context, state) {
      // While auth state is resolving, or when Firebase isn't configured,
      // don't gate navigation.
      if (auth.status == AuthStatus.unknown ||
          auth.status == AuthStatus.unconfigured) {
        return null;
      }
      final loggingIn = _authRoutes.contains(state.matchedLocation);
      if (!auth.isSignedIn) {
        return loggingIn ? null : '/auth';
      }
      // Signed in but sitting on an auth/splash screen → send into the app
      // (new light Home from the Figma redesign).
      if (loggingIn || state.matchedLocation == '/') {
        return '/home-v2';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const WelcomeScreen(),
      ),
      GoRoute(
        path: '/auth',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/auth/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      GoRoute(
        path: '/auth/reset',
        builder: (context, state) => const ResetPasswordScreen(),
      ),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      // --- New light-theme app flow (Figma frames 11–21) ---
      GoRoute(
        path: '/home-v2',
        builder: (context, state) => const HomeV2Screen(),
      ),
      GoRoute(
        path: '/orders',
        builder: (context, state) => const OrdersScreen(),
      ),
      GoRoute(
        path: '/profile-v2',
        builder: (context, state) => const ProfileV2Screen(),
      ),
      GoRoute(
        path: '/measure',
        builder: (context, state) => const AddMeasurementsScreen(),
      ),
      GoRoute(
        path: '/avatar',
        builder: (context, state) {
          final extra = state.extra;
          if (extra is Map) {
            return AvatarScreen(
              gender: extra['gender'] as String?,
              measurements: extra['measurements'] as BlouseMeasurements?,
              garmentId: extra['garment'] as String?,
            );
          }
          return const AvatarScreen();
        },
      ),
      GoRoute(
        path: '/measure/manual',
        builder: (context, state) => const ManualEntryScreen(),
      ),
      GoRoute(
        path: '/measure/capture',
        builder: (context, state) => const CaptureImagesScreen(),
      ),
      GoRoute(
        path: '/measure/review',
        builder: (context, state) => const ReviewMeasurementsScreen(),
      ),
      GoRoute(
        path: '/measure/persona',
        builder: (context, state) => const CreatePersonaScreen(),
      ),
      GoRoute(
        path: '/measure/saved',
        builder: (context, state) {
          final extra = state.extra;
          if (extra is Map) {
            return PersonaSavedScreen(
              personaName: extra['name'] as String?,
              gender: extra['gender'] as String? ?? 'female',
            );
          }
          // Back-compat: older callers passed just the name string.
          return PersonaSavedScreen(personaName: extra as String?);
        },
      ),
      GoRoute(
        path: '/persona',
        builder: (context, state) {
          final extra = state.extra;
          if (extra is Persona) return PersonaDetailScreen(persona: extra);
          return const Scaffold(body: Center(child: Text('No persona')));
        },
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
          final name = state.pathParameters['view'];
          CaptureView? view;
          if (name != null) {
            for (final v in CaptureView.values) {
              if (v.name == name) {
                view = v;
                break;
              }
            }
          }
          if (view == null) {
            return const Scaffold(
              body: Center(child: Text('Invalid capture step')),
            );
          }
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
      GoRoute(
        path: '/vest',
        builder: (context, state) => const VestScanScreen(),
      ),
      GoRoute(
        path: '/vest/result',
        builder: (context, state) {
          final extra = state.extra;
          if (extra is VestScanResult) {
            return VestResultScreen(result: extra);
          }
          return const Scaffold(body: Center(child: Text('No vest result')));
        },
      ),
      GoRoute(
        path: '/history/scan/:scanId',
        builder: (context, state) {
          final extra = state.extra;
          return ScanDetailScreen(
            scanId: state.pathParameters['scanId']!,
            initialScan: extra is ScanRecord ? extra : null,
          );
        },
      ),
    ],
  );
}

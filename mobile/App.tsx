/**
 * App.tsx
 * -------
 * PURPOSE:
 *   Root of the React Native application. Defines the navigation tree and
 *   wraps everything in the AuthProvider so all screens share auth state.
 *
 * CONCEPT — React Navigation
 *   React Navigation is the standard routing library for React Native.
 *   It works differently from web routing because there is no URL bar:
 *
 *   - NavigationContainer  — required root wrapper, holds navigation state
 *   - createNativeStackNavigator  — iOS/Android native screen transitions
 *   - createBottomTabNavigator   — tab bar at the bottom (Phase 8)
 *
 *   Stacks work like a history stack: navigate() pushes a screen, goBack()
 *   pops it. The back gesture/button is handled automatically.
 *
 * CONCEPT — Protected Navigation (Auth Guard)
 *   There is no "redirect" like in web apps. Instead we render different
 *   navigators based on whether the user is logged in:
 *
 *     isLoading → show a splash/loading screen
 *     user === null → render AuthStack  (Login, Register, ForgotPassword)
 *     user !== null → render based on role:
 *       user.role === 'admin' → AdminTabNavigator (Chat + Admin tabs)
 *       user.role === 'user'  → ChatNavigator (stack only, no tabs)
 *
 * CONCEPT — Nested Navigators
 *   The admin tab navigator contains two nested stack navigators:
 *     Tab "Chats" → ChatStack  (Home → Chat)
 *     Tab "Admin" → AdminStack (AdminHome → DocumentList → UploadDocument)
 *
 *   Each stack is independent — back navigation works within its own history.
 *
 * CONCEPT — TypeScript param types for navigators
 *   Each navigator declares a ParamList type that maps screen name → params.
 *   This gives type-safe navigation.navigate('Chat', { department: 'hr' })
 *   and catches typos at compile time.
 *
 * NAVIGATION TREE:
 *   <NavigationContainer>
 *     if !user:
 *       AuthStack  →  Login | Register | ForgotPassword
 *     if user.role === 'user':
 *       ChatStack  →  Home | Chat
 *     if user.role === 'admin':
 *       AdminTab:
 *         Chats tab  → ChatStack  → Home | Chat
 *         Admin tab  → AdminStack → AdminHome | DocumentList | UploadDocument
 */

import React from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

import { AuthProvider, useAuth } from './context/AuthContext';
import { Colors } from './theme';

import LoginScreen           from './screens/LoginScreen';
import RegisterScreen        from './screens/RegisterScreen';
import ForgotPasswordScreen  from './screens/ForgotPasswordScreen';
import HomeScreen            from './screens/HomeScreen';
import ChatScreen            from './screens/ChatScreen';
import AdminHomeScreen       from './screens/admin/AdminHomeScreen';
import DocumentListScreen    from './screens/admin/DocumentListScreen';
import UploadDocumentScreen  from './screens/admin/UploadDocumentScreen';
import { DepartmentKey }     from './screens/HomeScreen';

// ── TypeScript param lists ────────────────────────────────────────────────────
export type AuthStackParamList = {
  Login:          undefined;
  Register:       undefined;
  ForgotPassword: undefined;
};

// MainStackParamList is kept as the public name — used by HomeScreen and ChatScreen.
export type MainStackParamList = {
  Home: undefined;
  Chat: { department: DepartmentKey; departmentLabel: string };
};

export type AdminStackParamList = {
  AdminHome:       undefined;
  DocumentList:    { department: DepartmentKey; departmentLabel: string };
  UploadDocument:  { department: DepartmentKey; departmentLabel: string };
};

export type AdminTabParamList = {
  Chats: undefined;
  Admin: undefined;
};

// ── Navigator instances ────────────────────────────────────────────────────────
const AuthStack  = createNativeStackNavigator<AuthStackParamList>();
const ChatStack  = createNativeStackNavigator<MainStackParamList>();
const AdminStack = createNativeStackNavigator<AdminStackParamList>();
const AdminTab   = createBottomTabNavigator<AdminTabParamList>();

// ── Shared header options ─────────────────────────────────────────────────────
const navyHeader = {
  headerStyle:      { backgroundColor: Colors.navy },
  headerTintColor:  '#fff' as const,
  headerTitleStyle: { fontWeight: '700' as const },
  headerBackTitle:  '',
};

// ── Auth navigator ────────────────────────────────────────────────────────────
function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={navyHeader}>
      <AuthStack.Screen name="Login"          component={LoginScreen}
        options={{ headerShown: false }} />
      <AuthStack.Screen name="Register"       component={RegisterScreen}
        options={{ title: 'Create Account' }} />
      <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen}
        options={{ title: 'Reset Password' }} />
    </AuthStack.Navigator>
  );
}

// ── Chat navigator (Home → Chat) ──────────────────────────────────────────────
function ChatNavigator() {
  return (
    <ChatStack.Navigator screenOptions={navyHeader}>
      <ChatStack.Screen name="Home" component={HomeScreen}
        options={{ headerShown: false }} />
      <ChatStack.Screen name="Chat" component={ChatScreen}
        options={{ headerShown: false }} />
    </ChatStack.Navigator>
  );
}

// ── Admin navigator (AdminHome → DocumentList → UploadDocument) ───────────────
function AdminNavigator() {
  return (
    <AdminStack.Navigator screenOptions={navyHeader}>
      <AdminStack.Screen name="AdminHome"      component={AdminHomeScreen}
        options={{ headerShown: false }} />
      <AdminStack.Screen name="DocumentList"   component={DocumentListScreen}
        options={navyHeader} />
      <AdminStack.Screen name="UploadDocument" component={UploadDocumentScreen}
        options={{ ...navyHeader, title: 'Upload Document' }} />
    </AdminStack.Navigator>
  );
}

// ── Admin tab navigator (Chat tab + Admin tab) ────────────────────────────────
function AdminTabNavigator() {
  return (
    <AdminTab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor:   Colors.indigo,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopColor:  Colors.border,
          paddingTop: 4,
          height: 60,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '700', paddingBottom: 6 },
        tabBarIcon: ({ color }) => {
          const icon = route.name === 'Chats' ? '💬' : '🗂️';
          return <Text style={{ fontSize: 20, color }}>{icon}</Text>;
        },
      })}
    >
      <AdminTab.Screen name="Chats" component={ChatNavigator}  options={{ title: 'Chats' }} />
      <AdminTab.Screen name="Admin" component={AdminNavigator} options={{ title: 'Admin' }} />
    </AdminTab.Navigator>
  );
}

// ── Root — switches Auth ↔ Main based on login state + role ──────────────────
function Root() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.navy }}>
        <ActivityIndicator size="large" color="#fff" />
      </View>
    );
  }

  if (!user) return <AuthNavigator />;
  if (user.role === 'admin') return <AdminTabNavigator />;
  return <ChatNavigator />;
}

// ── App entry point ───────────────────────────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <Root />
      </NavigationContainer>
    </AuthProvider>
  );
}

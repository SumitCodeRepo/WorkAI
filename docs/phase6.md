# Phase 6 — React Native App Setup + Auth Screens

## Concept to Learn

### 1. Expo Managed Workflow

Expo is a framework and toolchain built around React Native. The "managed" workflow means:

- **No native code files** (no `android/` or `ios/` directories to maintain)
- Expo manages native builds for you via `expo build` or EAS Build
- `expo start` launches Metro bundler + Expo Go app on device/emulator

```bash
npx create-expo-app mobile --template blank-typescript
cd mobile
npx expo start        # start dev server
```

**Expo Go** is a companion app on your phone. Scan the QR code from `expo start` and your app runs on the device immediately — no cable, no Xcode, no Android Studio needed during development.

### 2. React Navigation

React Navigation is the standard routing library for React Native. Unlike the web (where the browser manages URL history), React Native has no URL bar — navigation is purely in-memory.

**Key concepts:**

| Concept | Web analogy | React Navigation |
|---|---|---|
| History stack | Browser history | Stack Navigator |
| Current page | URL | Active screen name |
| Navigate | `<a href>` / `router.push()` | `navigation.navigate('Screen')` |
| Go back | Browser back button | `navigation.goBack()` / swipe gesture |
| Tab bar | None (web uses links) | Bottom Tab Navigator |

**Setup:**
```tsx
<NavigationContainer>          // required root wrapper
  <Stack.Navigator>
    <Stack.Screen name="Login" component={LoginScreen} />
    <Stack.Screen name="Register" component={RegisterScreen} />
  </Stack.Navigator>
</NavigationContainer>
```

### 3. TypeScript Param Lists

Each navigator declares a type that maps screen names to their required params. This gives compile-time safety:

```typescript
export type AuthStackParamList = {
  Login:          undefined;          // no params
  Register:       undefined;
  ForgotPassword: undefined;
  Chat:           { department: string };  // requires a param
};

// Type-safe navigation:
navigation.navigate('Chat', { department: 'hr' });   // ✅
navigation.navigate('Chat');                          // ❌ TypeScript error
navigation.navigate('Chaat', { department: 'hr' });  // ❌ typo caught
```

### 4. React Context API (AuthContext)

Context solves "prop drilling" — passing a value (like the current user) down through many component layers.

```
App
  ├── AuthProvider          ← holds user state
  │     ├── HomeScreen      ← calls useAuth() → gets user
  │     ├── ChatScreen      ← calls useAuth() → gets token
  │     └── AdminScreen     ← calls useAuth() → gets user.role
```

Pattern:
1. `createContext()` — creates the context object
2. `<AuthProvider>` — wraps the app, holds state with `useState`
3. `useAuth()` — any child calls this hook to read or update state

### 5. AsyncStorage (Persistent Token)

React Native has no `localStorage`. AsyncStorage is the equivalent:
- Key-value store, persists across app restarts
- All operations are **async** (native bridge is async)
- Used to store the JWT token so the user stays logged in

```typescript
await AsyncStorage.setItem('auth_token', token);   // save
const token = await AsyncStorage.getItem('auth_token');  // read
await AsyncStorage.removeItem('auth_token');        // delete (logout)
```

### 6. Axios Interceptors

An interceptor runs on every request or response before it reaches your component:

```typescript
// Request interceptor — attaches JWT to every API call automatically
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('auth_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

Without this: every screen must manually add `headers: { Authorization: ... }`.
With this: write it once, it applies to all 50+ future API calls.

### 7. Auth-Based Navigator Switching (Protected Routes)

There are no "protected routes" in React Native like in React Router. Instead, render different navigators based on auth state:

```tsx
function Root() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <SplashScreen />;
  return user ? <MainNavigator /> : <AuthNavigator />;
}
```

When `login()` sets `user`, React re-renders `Root` and `MainNavigator` replaces `AuthNavigator` automatically. The user never sees the Login screen again until they log out.

### 8. BASE_URL for Devices

`localhost` on a physical device refers to the **device itself**, not your development machine:

| Environment | BASE_URL |
|---|---|
| Android Emulator | `http://10.0.2.2:8000` (special alias for host) |
| iOS Simulator | `http://localhost:8000` |
| Physical device | `http://192.168.x.x:8000` (your machine's LAN IP) |
| Expo Go on device | Same as physical device |

---

## What Was Built

### Files Created

| File | Description |
|---|---|
| `mobile/` | Expo managed TypeScript project (scaffolded) |
| `mobile/theme.ts` | Design tokens: Colors, Typography, Shadow, Spacing |
| `mobile/services/api.ts` | Axios instance + request interceptor + auth endpoints |
| `mobile/context/AuthContext.tsx` | Global auth state: user, token, login, logout, isLoading |
| `mobile/screens/LoginScreen.tsx` | Email + password login form |
| `mobile/screens/RegisterScreen.tsx` | Registration form with department chip selector |
| `mobile/screens/ForgotPasswordScreen.tsx` | Email input → sends reset link → step confirmation |
| `mobile/screens/HomeScreen.tsx` | 5 department cards + recent conversations |
| `mobile/App.tsx` | Navigation tree: AuthStack ↔ MainStack based on auth state |
| `docs/phase6.md` | This document |

### Dependencies Installed

```
@react-navigation/native
@react-navigation/native-stack
@react-navigation/bottom-tabs
axios
@react-native-async-storage/async-storage
react-native-safe-area-context
react-native-screens
react-native-gesture-handler
react-native-reanimated
```

---

## Navigation Flow

```
App startup
    │
    ▼
AuthContext.isLoading = true
    │  (check AsyncStorage for stored token)
    ▼
No token → AuthNavigator     Token found → validate with GET /auth/me
    │                                           │
    │                               Valid → MainNavigator
    │                               Invalid → AsyncStorage.clear → AuthNavigator
    │
 [Login screen]
    │  user enters email + password
    │  POST /auth/login
    │  save token to AsyncStorage
    │  fetch user with GET /auth/me
    │
    ▼
 AuthContext.user is set → Root re-renders → MainNavigator
    │
 [Home screen]
    │  5 department cards
    │  navigate('Chat', { department: 'hr' })  ← Phase 7
```

---

## Auth Screens Detail

### LoginScreen
- Controlled inputs: email (email keyboard) + password (secureTextEntry)
- `KeyboardAvoidingView` keeps inputs above the software keyboard
- `handleLogin()` calls `useAuth().login()` → AuthContext → API → token saved
- Wrong credentials → Alert with API error message
- "Forgot password?" → ForgotPasswordScreen
- "Create one" → RegisterScreen

### RegisterScreen
- Full name, email, password, confirm password fields
- Department selector: 5 touch-chip buttons (HR, IT, Finance, Legal, Admin)
- Client-side validation: empty fields, password mismatch, length
- On success: Alert → navigate back to Login

### ForgotPasswordScreen
- Two states: **input** (email form) and **success** (step progress view)
- Success state shows: animated ✅, email address, 3-step tracker
- Resend: puts user back to input state
- TODO Phase 9: replace `setTimeout` mock with real `POST /auth/forgot-password`

### HomeScreen
- Navy header with user's first name (from `useAuth().user.full_name`)
- Avatar circle (tapping it logs out — good for prototype/testing)
- 2-column card grid, last card full-width if odd count
- 3 recent conversation rows (static placeholders until Phase 7 adds real history)
- Each card navigates to Chat with `{ department, departmentLabel }` params

---

## Running the App

```bash
cd mobile/

# Android emulator (ensure emulator is running first)
npx expo start --android

# iOS simulator (Mac only)
npx expo start --ios

# Expo Go on physical device
npx expo start
# Scan QR code with Expo Go app
```

**Before running:** ensure the FastAPI backend is running:
```bash
cd backend/
..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000
```

---

## Known Issues / Notes

- `BASE_URL` in `services/api.ts` is set to `http://10.0.2.2:8000` (Android emulator). Change to your machine's LAN IP for physical device testing.
- `--legacy-peer-deps` was required during `npm install` due to a version conflict between `react-native-screens` and `@react-navigation/native-stack`. This is a known transient issue and does not affect runtime behaviour.
- The `Chat` screen in `MainStackParamList` is declared but the screen component is not yet registered — it is added in Phase 7.
- The avatar tap calls `logout()` — convenient for testing the auth flow without a settings screen.

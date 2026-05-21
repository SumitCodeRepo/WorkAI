/**
 * screens/LoginScreen.tsx
 * -----------------------
 * PURPOSE:
 *   Email + password login form. On success, AuthContext updates the global
 *   user state and navigation automatically redirects to the main app.
 *
 * CONCEPT — Controlled Inputs in React Native
 *   React Native's <TextInput> uses value + onChangeText instead of the
 *   browser's onChange event. State drives what's displayed; user typing
 *   calls the setter. This is the same "controlled component" pattern as React.
 *
 * CONCEPT — KeyboardAvoidingView
 *   On mobile, the software keyboard slides up and covers the bottom of the
 *   screen. KeyboardAvoidingView automatically adjusts its content so inputs
 *   remain visible. Use behavior="padding" on iOS, "height" on Android
 *   (or detect platform with Platform.OS).
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useAuth } from '../context/AuthContext';
import { AuthStackParamList } from '../App';
import { Colors, Typography, Spacing } from '../theme';
import { checkHealth, HealthStatus } from '../services/api';

type Props = NativeStackScreenProps<AuthStackParamList, 'Login'>;

function healthLabel(s: HealthStatus | 'checking') {
  if (s === 'checking')    return 'Checking API…';
  if (s === 'ok')          return 'API Online';
  if (s === 'degraded')    return 'API Degraded';
  return 'API Unreachable';
}

function healthDotColor(s: HealthStatus | 'checking') {
  if (s === 'ok')       return { backgroundColor: '#22c55e' };
  if (s === 'degraded') return { backgroundColor: '#f59e0b' };
  if (s === 'checking') return { backgroundColor: '#94a3b8' };
  return { backgroundColor: '#ef4444' };
}

export default function LoginScreen({ navigation }: Props) {
  const { login } = useAuth();
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [loading,  setLoading]  = useState(false);
  const [health,   setHealth]   = useState<HealthStatus | 'checking'>('checking');

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      Alert.alert('Missing fields', 'Please enter your email and password.');
      return;
    }
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
      // Navigation happens automatically — App.tsx watches auth state.
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Login failed. Please try again.';
      Alert.alert('Sign In Failed', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* ── Header ── */}
        <View style={styles.header}>
          <View style={styles.iconWrap}>
            <Text style={styles.iconText}>🤖 TET</Text>
          </View>
          <Text style={styles.appName}>WorkAI Demo</Text>
          <Text style={styles.tagline}>Your intelligent workplace assistant</Text>
        </View>

        {/* ── Form ── */}
        <View style={styles.form}>
          <View style={styles.field}>
            <Text style={styles.label}>EMAIL ADDRESS</Text>
            <TextInput
              style={styles.input}
              placeholder="you@company.com"
              placeholderTextColor={Colors.placeholder}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              value={email}
              onChangeText={setEmail}
            />
          </View>

          <View style={styles.field}>
            <View style={styles.labelRow}>
              <Text style={styles.label}>PASSWORD</Text>
              <TouchableOpacity onPress={() => navigation.navigate('ForgotPassword')}>
                <Text style={styles.forgotLink}>Forgot password?</Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              placeholderTextColor={Colors.placeholder}
              secureTextEntry
              autoComplete="password"
              value={password}
              onChangeText={setPassword}
              onSubmitEditing={handleLogin}
              returnKeyType="go"
            />
          </View>

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnDisabled]}
            onPress={handleLogin}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>Sign In →</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity onPress={() => navigation.navigate('Register')}>
            <Text style={styles.linkText}>
              Don't have an account?{' '}
              <Text style={styles.link}>Create one</Text>
            </Text>
          </TouchableOpacity>

          <View style={styles.healthRow}>
            <View style={[styles.healthDot, healthDotColor(health)]} />
            <Text style={styles.healthText}>{healthLabel(health)}</Text>
          </View>

          <Text style={styles.footer}>🔒 All data encrypted · JWT authentication</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#fff' },
  scroll: { flexGrow: 1 },

  header: {
    backgroundColor: Colors.navy,
    paddingTop: 80,
    paddingBottom: 56,
    paddingHorizontal: 32,
    alignItems: 'center',
    borderBottomLeftRadius: 40,
    borderBottomRightRadius: 40,
  },
  iconWrap: {
    width: 72, height: 72, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
  },
  iconText:  { fontSize: 36 },
  appName:   { ...Typography.h1, color: '#fff', letterSpacing: -0.5 },
  tagline:   { ...Typography.caption, color: 'rgba(255,255,255,0.7)', marginTop: 6 },

  form: { padding: 24, gap: 16 },
  field: { gap: 6 },
  label: { ...Typography.label },
  labelRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  forgotLink: { fontSize: 12, color: Colors.indigo, fontWeight: '600' },

  input: {
    height: 52, borderWidth: 1.5, borderColor: Colors.border, borderRadius: 10,
    paddingHorizontal: 16, fontSize: 15, color: Colors.text, backgroundColor: '#fff',
  },

  btn: {
    height: 54, backgroundColor: Colors.indigo, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center', marginTop: 8,
  },
  btnDisabled: { opacity: 0.7 },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '700' },

  linkText: { textAlign: 'center', fontSize: 14, color: Colors.muted, marginTop: 4 },
  link:     { color: Colors.indigo, fontWeight: '600' },

  healthRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 16 },
  healthDot: { width: 8, height: 8, borderRadius: 4 },
  healthText: { fontSize: 12, color: Colors.muted, fontWeight: '500' },

  footer:   { textAlign: 'center', fontSize: 11, color: Colors.muted, marginTop: 8 },
});

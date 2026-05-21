/**
 * screens/ForgotPasswordScreen.tsx
 * ---------------------------------
 * PURPOSE:
 *   Lets a user request a password reset email.
 *   The backend (Phase 9) will send the actual email; for now the screen
 *   shows the success state immediately to demonstrate the full UI flow.
 *
 * NOTE:
 *   The backend does not yet have a password-reset endpoint. When Phase 9
 *   adds it (POST /auth/forgot-password), replace the fake success below
 *   with a real API call.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AuthStackParamList } from '../App';
import { Colors, Typography } from '../theme';

type Props = NativeStackScreenProps<AuthStackParamList, 'ForgotPassword'>;

export default function ForgotPasswordScreen({ navigation }: Props) {
  const [email,   setEmail]   = useState('');
  const [loading, setLoading] = useState(false);
  const [sent,    setSent]    = useState(false);

  const handleSend = async () => {
    if (!email.trim()) {
      Alert.alert('Email required', 'Please enter your work email address.');
      return;
    }
    setLoading(true);
    try {
      // TODO Phase 9: await api.post('/auth/forgot-password', { email })
      await new Promise(r => setTimeout(r, 1000)); // simulate network call
      setSent(true);
    } catch {
      Alert.alert('Error', 'Could not send reset email. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Success state ─────────────────────────────────────────────────────────
  if (sent) {
    return (
      <View style={styles.successWrap}>
        <View style={styles.successIcon}>
          <Text style={{ fontSize: 48 }}>✅</Text>
        </View>
        <Text style={styles.successTitle}>Email Sent!</Text>
        <Text style={styles.successBody}>
          We've sent a password reset link to{'\n'}
          <Text style={{ fontWeight: '700', color: Colors.text }}>{email}</Text>
        </Text>

        {/* Step tracker */}
        <View style={styles.steps}>
          {[
            { done: true,  label: 'Reset email sent',       sub: 'Link expires in 30 minutes' },
            { done: false, label: 'Click the link in email', sub: 'Opens a secure reset page' },
            { done: false, label: 'Choose a new password',   sub: 'Min. 8 characters' },
          ].map((s, i) => (
            <View key={i} style={styles.stepRow}>
              <View style={[styles.stepDot, s.done && styles.stepDotDone]}>
                <Text style={[styles.stepNum, s.done && styles.stepNumDone]}>
                  {s.done ? '✓' : String(i + 1)}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.stepLabel, !s.done && styles.stepLabelMuted]}>{s.label}</Text>
                <Text style={styles.stepSub}>{s.sub}</Text>
              </View>
            </View>
          ))}
        </View>

        <TouchableOpacity style={styles.btn} onPress={() => navigation.navigate('Login')}>
          <Text style={styles.btnText}>Back to Sign In</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.outlineBtn} onPress={() => setSent(false)}>
          <Text style={styles.outlineBtnText}>Resend Email</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Input state ───────────────────────────────────────────────────────────
  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* Illustration */}
        <View style={styles.illustration}>
          <View style={styles.illustrationIcon}>
            <Text style={{ fontSize: 40 }}>🔑</Text>
          </View>
          <Text style={styles.ilTitle}>Forgot your password?</Text>
          <Text style={styles.ilBody}>
            No worries. Enter your work email and we'll send a reset link to your inbox.
          </Text>
        </View>

        <View style={styles.form}>
          <View style={styles.field}>
            <Text style={styles.label}>WORK EMAIL ADDRESS</Text>
            <TextInput
              style={styles.input}
              placeholder="you@company.com"
              placeholderTextColor={Colors.placeholder}
              autoCapitalize="none"
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
              onSubmitEditing={handleSend}
              returnKeyType="send"
            />
          </View>

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnDisabled]}
            onPress={handleSend}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>Send Reset Link →</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity onPress={() => navigation.navigate('Login')}>
            <Text style={styles.linkText}>
              Remembered it?{' '}
              <Text style={styles.link}>Back to Sign In</Text>
            </Text>
          </TouchableOpacity>

          {/* Info box */}
          <View style={styles.infoBox}>
            <Text style={styles.infoTitle}>What happens next?</Text>
            {[
              'Check your inbox for noreply@workai.company.com',
              'Click the secure link (valid for 30 minutes)',
              'Choose a new password (min. 8 characters)',
            ].map((t, i) => (
              <Text key={i} style={styles.infoItem}>{i + 1}. {t}</Text>
            ))}
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex:   { flex: 1, backgroundColor: '#fff' },
  scroll: { flexGrow: 1 },

  illustration: {
    backgroundColor: Colors.bg, padding: 40, alignItems: 'center',
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  illustrationIcon: {
    width: 80, height: 80, borderRadius: 24, backgroundColor: Colors.navy,
    alignItems: 'center', justifyContent: 'center', marginBottom: 20,
  },
  ilTitle: { ...Typography.h2, textAlign: 'center' },
  ilBody:  { ...Typography.body, color: Colors.muted, textAlign: 'center', marginTop: 8, lineHeight: 22 },

  form:  { padding: 24, gap: 16 },
  field: { gap: 6 },
  label: { ...Typography.label },
  input: {
    height: 52, borderWidth: 1.5, borderColor: Colors.border, borderRadius: 10,
    paddingHorizontal: 16, fontSize: 15, color: Colors.text,
  },

  btn:         { height: 54, backgroundColor: Colors.indigo, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  btnDisabled: { opacity: 0.7 },
  btnText:     { color: '#fff', fontSize: 16, fontWeight: '700' },

  outlineBtn:     { height: 48, borderWidth: 1.5, borderColor: Colors.indigo, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  outlineBtnText: { color: Colors.indigo, fontSize: 15, fontWeight: '600' },

  linkText: { textAlign: 'center', fontSize: 14, color: Colors.muted },
  link:     { color: Colors.indigo, fontWeight: '600' },

  infoBox:   { backgroundColor: Colors.bg, borderRadius: 12, padding: 16, gap: 6 },
  infoTitle: { fontSize: 13, fontWeight: '700', color: Colors.text, marginBottom: 4 },
  infoItem:  { fontSize: 13, color: Colors.muted, lineHeight: 20 },

  // Success state
  successWrap: { flex: 1, backgroundColor: '#fff', padding: 24, alignItems: 'center', justifyContent: 'center', gap: 16 },
  successIcon: { width: 96, height: 96, borderRadius: 48, backgroundColor: '#DCFCE7', alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  successTitle: { ...Typography.h1, textAlign: 'center' },
  successBody:  { fontSize: 15, color: Colors.muted, textAlign: 'center', lineHeight: 24 },

  steps:       { width: '100%', backgroundColor: Colors.bg, borderRadius: 16, padding: 20, gap: 14 },
  stepRow:     { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  stepDot:     { width: 28, height: 28, borderRadius: 14, backgroundColor: Colors.border, alignItems: 'center', justifyContent: 'center' },
  stepDotDone: { backgroundColor: Colors.success },
  stepNum:     { fontSize: 13, fontWeight: '700', color: Colors.muted },
  stepNumDone: { color: '#fff' },
  stepLabel:      { fontSize: 13, fontWeight: '600', color: Colors.text },
  stepLabelMuted: { color: Colors.muted },
  stepSub:     { fontSize: 12, color: Colors.muted, marginTop: 2 },
});

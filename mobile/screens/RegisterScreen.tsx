/**
 * screens/RegisterScreen.tsx
 * --------------------------
 * PURPOSE:
 *   New user registration. Calls POST /auth/register then navigates back
 *   to Login with a success message.
 *
 * CONCEPT — Picker / Select in React Native
 *   There is no native <select> in React Native. Common approaches:
 *     a) A modal with a FlatList of options (full control, most work)
 *     b) @react-native-picker/picker (native OS picker, minimal UI)
 *     c) A simple TouchableOpacity that opens a custom dropdown
 *   We use approach (c) here — a row of touchable chips — to avoid adding
 *   another dependency and to keep the UI consistent with the prototype.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { authApi } from '../services/api';
import { AuthStackParamList } from '../App';
import { Colors, Typography } from '../theme';

type Props = NativeStackScreenProps<AuthStackParamList, 'Register'>;

const DEPARTMENTS = [
  { value: 'hr',      label: 'HR' },
  { value: 'it',      label: 'IT' },
  { value: 'finance', label: 'Finance' },
  { value: 'legal',   label: 'Legal' },
  { value: 'admin',   label: 'Admin' },
];

export default function RegisterScreen({ navigation }: Props) {
  const [fullName,   setFullName]   = useState('');
  const [email,      setEmail]      = useState('');
  const [password,   setPassword]   = useState('');
  const [confirm,    setConfirm]    = useState('');
  const [department, setDepartment] = useState('');
  const [loading,    setLoading]    = useState(false);

  const handleRegister = async () => {
    if (!fullName.trim() || !email.trim() || !password || !confirm) {
      Alert.alert('Missing fields', 'Please fill in all required fields.');
      return;
    }
    if (password !== confirm) {
      Alert.alert('Password mismatch', 'Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      Alert.alert('Weak password', 'Password must be at least 8 characters.');
      return;
    }

    setLoading(true);
    try {
      await authApi.register({
        email:      email.trim().toLowerCase(),
        password,
        full_name:  fullName.trim(),
        department: department || 'general',
      });
      Alert.alert(
        'Account created!',
        'You can now sign in with your credentials.',
        [{ text: 'Sign In', onPress: () => navigation.navigate('Login') }],
      );
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Registration failed.';
      Alert.alert('Error', msg);
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
        <View style={styles.form}>
          <Text style={styles.subtitle}>
            Fill in your details to request access to WorkAI.
          </Text>

          <View style={styles.field}>
            <Text style={styles.label}>FULL NAME</Text>
            <TextInput style={styles.input} placeholder="Sarah Lee"
              placeholderTextColor={Colors.placeholder}
              value={fullName} onChangeText={setFullName} />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>WORK EMAIL</Text>
            <TextInput style={styles.input} placeholder="you@company.com"
              placeholderTextColor={Colors.placeholder}
              autoCapitalize="none" keyboardType="email-address"
              value={email} onChangeText={setEmail} />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>PASSWORD</Text>
            <TextInput style={styles.input} placeholder="Min. 8 characters"
              placeholderTextColor={Colors.placeholder}
              secureTextEntry value={password} onChangeText={setPassword} />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>CONFIRM PASSWORD</Text>
            <TextInput style={styles.input} placeholder="Repeat password"
              placeholderTextColor={Colors.placeholder}
              secureTextEntry value={confirm} onChangeText={setConfirm} />
          </View>

          {/* Department chips */}
          <View style={styles.field}>
            <Text style={styles.label}>YOUR DEPARTMENT</Text>
            <View style={styles.chips}>
              {DEPARTMENTS.map(d => (
                <TouchableOpacity
                  key={d.value}
                  style={[styles.chip, department === d.value && styles.chipActive]}
                  onPress={() => setDepartment(d.value)}
                >
                  <Text style={[styles.chipText, department === d.value && styles.chipTextActive]}>
                    {d.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnDisabled]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>Create Account →</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity onPress={() => navigation.navigate('Login')}>
            <Text style={styles.linkText}>
              Already have an account?{' '}
              <Text style={styles.link}>Sign in</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex:   { flex: 1, backgroundColor: '#fff' },
  scroll: { flexGrow: 1 },
  form:   { padding: 24, gap: 16 },

  subtitle: { fontSize: 14, color: Colors.muted, lineHeight: 20 },
  field:    { gap: 6 },
  label:    { ...Typography.label },

  input: {
    height: 52, borderWidth: 1.5, borderColor: Colors.border, borderRadius: 10,
    paddingHorizontal: 16, fontSize: 15, color: Colors.text, backgroundColor: '#fff',
  },

  chips:        { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip:         { paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20, borderWidth: 1.5, borderColor: Colors.border },
  chipActive:   { borderColor: Colors.indigo, backgroundColor: '#EEF2FF' },
  chipText:     { fontSize: 13, fontWeight: '600', color: Colors.muted },
  chipTextActive: { color: Colors.indigo },

  btn:         { height: 54, backgroundColor: Colors.indigo, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  btnDisabled: { opacity: 0.7 },
  btnText:     { color: '#fff', fontSize: 16, fontWeight: '700' },

  linkText: { textAlign: 'center', fontSize: 14, color: Colors.muted, marginTop: 4 },
  link:     { color: Colors.indigo, fontWeight: '600' },
});

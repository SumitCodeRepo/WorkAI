/**
 * screens/HomeScreen.tsx
 * ----------------------
 * PURPOSE:
 *   Main landing screen after login. Shows 5 department cards; tapping one
 *   opens a ChatScreen for that department.
 *
 * CONCEPT — FlatList vs ScrollView
 *   ScrollView renders ALL children at once — fine for a short list of cards.
 *   FlatList renders only what's visible on screen (virtualised) — essential
 *   for long lists (100+ items) to keep memory and frame rate acceptable.
 *   Here we use ScrollView because we always have exactly 5 cards.
 *
 * CONCEPT — Bottom Tab Navigator
 *   The tab bar at the bottom is managed by @react-navigation/bottom-tabs.
 *   The HomeScreen is one tab; AdminHomeScreen (Phase 8) will be another.
 *   The tab bar is defined in App.tsx, not here — this screen just renders
 *   its own content inside the tab container.
 */

import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useAuth } from '../context/AuthContext';
import { Colors, Shadow, Typography } from '../theme';
import { MainStackParamList } from '../App';

type Props = NativeStackScreenProps<MainStackParamList, 'Home'>;

const DEPARTMENTS = [
  { key: 'hr',      label: 'Human Resources', icon: '👥', desc: 'Leave, payroll, benefits & conduct' },
  { key: 'it',      label: 'IT Support',       icon: '💻', desc: 'Access, VPN, software & hardware' },
  { key: 'finance', label: 'Finance',           icon: '💰', desc: 'Expenses, claims & approvals' },
  { key: 'legal',   label: 'Legal',             icon: '⚖️', desc: 'Contracts, NDAs & compliance' },
  { key: 'admin',   label: 'Administration',    icon: '📋', desc: 'Rooms, facilities & travel' },
] as const;

export type DepartmentKey = typeof DEPARTMENTS[number]['key'];

export default function HomeScreen({ navigation }: Props) {
  const { user, logout } = useAuth();

  const firstName = user?.full_name?.split(' ')[0] ?? 'there';

  return (
    <SafeAreaView style={styles.safe}>
      {/* ── Header ── */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Good morning 👋</Text>
          <Text style={styles.name}>{firstName}</Text>
        </View>
        <TouchableOpacity style={styles.avatar} onPress={logout}>
          <Text style={styles.avatarText}>
            {user?.full_name?.charAt(0).toUpperCase() ?? '?'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Search bar (decorative — search is Phase 9) */}
      <View style={styles.searchBar}>
        <Text style={styles.searchText}>🔍  Ask anything or choose a department…</Text>
      </View>

      {/* ── Department cards ── */}
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.sectionTitle}>Choose your department</Text>

        <View style={styles.grid}>
          {DEPARTMENTS.map((d, i) => {
            const colour = Colors[d.key as DepartmentKey];
            const isWide = i === DEPARTMENTS.length - 1 && DEPARTMENTS.length % 2 !== 0;
            return (
              <TouchableOpacity
                key={d.key}
                style={[styles.card, isWide && styles.cardWide, { shadowColor: colour.accent }]}
                onPress={() => navigation.navigate('Chat', { department: d.key, departmentLabel: d.label })}
                activeOpacity={0.85}
              >
                <View style={[styles.iconWrap, { backgroundColor: colour.bg }]}>
                  <Text style={styles.icon}>{d.icon}</Text>
                </View>
                <View style={styles.cardText}>
                  <Text style={styles.cardName}>{d.label}</Text>
                  <Text style={styles.cardDesc}>{d.desc}</Text>
                </View>
                <View style={[styles.dot, { backgroundColor: colour.accent }]} />
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Recent conversations placeholder */}
        <Text style={[styles.sectionTitle, { marginTop: 8 }]}>Recent Conversations</Text>
        {[
          { dept: 'hr',      label: 'HR Agent',      preview: 'You get 18 days of annual leave…',     time: '2h ago' },
          { dept: 'it',      label: 'IT Agent',      preview: 'Visit helpdesk.company.com to reset…', time: 'Yesterday' },
          { dept: 'finance', label: 'Finance Agent', preview: 'Submit expense claims within 30 days…', time: 'Mon' },
        ].map(r => (
          <TouchableOpacity
            key={r.dept}
            style={styles.recentItem}
            onPress={() => navigation.navigate('Chat', { department: r.dept as DepartmentKey, departmentLabel: r.label })}
            activeOpacity={0.8}
          >
            <View style={[styles.recentDot, { backgroundColor: Colors[r.dept as DepartmentKey].accent }]} />
            <View style={styles.recentContent}>
              <Text style={styles.recentDept}>{r.label}</Text>
              <Text style={styles.recentPreview} numberOfLines={1}>{r.preview}</Text>
            </View>
            <Text style={styles.recentTime}>{r.time}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },

  header: {
    backgroundColor: Colors.navy, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 8, paddingBottom: 16,
  },
  greeting: { fontSize: 12, color: 'rgba(255,255,255,0.6)', fontWeight: '500' },
  name:     { ...Typography.h2, color: '#fff', marginTop: 2 },
  avatar: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: Colors.indigo,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  searchBar: {
    backgroundColor: Colors.navy, paddingHorizontal: 20, paddingBottom: 16,
  },
  searchBarInner: {
    backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 10,
    height: 42, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14,
  },
  searchText: {
    backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 10, height: 42,
    paddingHorizontal: 14, textAlignVertical: 'center', lineHeight: 42,
    fontSize: 14, color: 'rgba(255,255,255,0.6)',
  },

  scroll: { padding: 16, paddingBottom: 32 },

  sectionTitle: {
    fontSize: 12, fontWeight: '700', color: Colors.muted,
    textTransform: 'uppercase', letterSpacing: 0.7, marginBottom: 12,
  },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 },

  card: {
    backgroundColor: '#fff', borderRadius: 16, padding: 16,
    width: '47.5%', ...Shadow.card,
  },
  cardWide: { width: '100%', flexDirection: 'row', alignItems: 'center', gap: 16 },

  iconWrap: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  icon:     { fontSize: 22 },
  cardText: { flex: 1, marginTop: 12 },
  cardName: { fontSize: 14, fontWeight: '700', color: Colors.text },
  cardDesc: { fontSize: 11, color: Colors.muted, marginTop: 4, lineHeight: 15 },
  dot:      { position: 'absolute', top: 14, right: 14, width: 8, height: 8, borderRadius: 4 },

  recentItem: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 8,
    flexDirection: 'row', alignItems: 'center', gap: 12, ...Shadow.card,
  },
  recentDot:     { width: 10, height: 10, borderRadius: 5 },
  recentContent: { flex: 1 },
  recentDept:    { fontSize: 13, fontWeight: '600', color: Colors.text },
  recentPreview: { fontSize: 12, color: Colors.muted, marginTop: 2 },
  recentTime:    { fontSize: 11, color: Colors.muted },
});

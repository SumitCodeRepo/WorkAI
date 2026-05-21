/**
 * screens/admin/AdminHomeScreen.tsx
 * -----------------------------------
 * PURPOSE:
 *   Admin landing screen. Shows all 5 departments as cards with their
 *   current document count. Tapping a card opens DocumentListScreen
 *   for that department.
 *
 * CONCEPT — Role-Based Navigation
 *   This screen is only reachable via the Admin tab, which itself is only
 *   rendered when useAuth().user.role === 'admin'. The backend also enforces
 *   admin role on every /admin/* endpoint via the require_admin dependency —
 *   so even if someone reaches this screen, API calls will 403 without the
 *   right role.
 *
 * CONCEPT — Parallel Data Fetching
 *   We fetch the full document list once and group by department client-side,
 *   rather than making 5 parallel requests. This is one network call and
 *   scales well for a small number of departments.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, SafeAreaView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';

import { adminApi, DocumentInfo } from '../../services/api';
import { Colors, Shadow } from '../../theme';
import { AdminStackParamList } from '../../App';
import { DepartmentKey } from '../HomeScreen';

type Props = NativeStackScreenProps<AdminStackParamList, 'AdminHome'>;

const DEPARTMENTS: { key: DepartmentKey; label: string; icon: string }[] = [
  { key: 'hr',      label: 'Human Resources', icon: '👥' },
  { key: 'it',      label: 'IT Support',       icon: '💻' },
  { key: 'finance', label: 'Finance',           icon: '💰' },
  { key: 'legal',   label: 'Legal',             icon: '⚖️' },
  { key: 'admin',   label: 'Administration',    icon: '📋' },
];

const DEPT_COLOR: Record<DepartmentKey, string> = {
  hr:      Colors.hr.accent,
  it:      Colors.it.accent,
  finance: Colors.finance.accent,
  legal:   Colors.legal.accent,
  admin:   Colors.admin.accent,
};

const DEPT_BG: Record<DepartmentKey, string> = {
  hr:      Colors.hr.bg,
  it:      Colors.it.bg,
  finance: Colors.finance.bg,
  legal:   Colors.legal.bg,
  admin:   Colors.admin.bg,
};

export default function AdminHomeScreen({ navigation }: Props) {
  const [docCounts, setDocCounts]   = useState<Record<string, number>>({});
  const [loading,   setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,     setError]       = useState<string | null>(null);

  const loadCounts = useCallback(async () => {
    try {
      const res = await adminApi.listDocuments();
      const counts: Record<string, number> = {};
      for (const doc of res.data as DocumentInfo[]) {
        counts[doc.department] = (counts[doc.department] ?? 0) + 1;
      }
      setDocCounts(counts);
      setError(null);
    } catch {
      setError('Failed to load document counts.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadCounts(); }, [loadCounts]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    loadCounts();
  }, [loadCounts]);

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.indigo} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Document Manager</Text>
        <Text style={styles.headerSub}>Tap a department to manage its knowledge base</Text>
      </View>

      {error && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <FlatList
        data={DEPARTMENTS}
        keyExtractor={d => d.key}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.indigo} />
        }
        renderItem={({ item: d }) => {
          const count = docCounts[d.key] ?? 0;
          return (
            <TouchableOpacity
              style={[styles.card, { borderLeftColor: DEPT_COLOR[d.key] }]}
              onPress={() => navigation.navigate('DocumentList', {
                department:      d.key,
                departmentLabel: d.label,
              })}
              activeOpacity={0.85}
            >
              <View style={[styles.iconWrap, { backgroundColor: DEPT_BG[d.key] }]}>
                <Text style={styles.icon}>{d.icon}</Text>
              </View>
              <View style={styles.cardBody}>
                <Text style={styles.cardTitle}>{d.label}</Text>
                <Text style={styles.cardSub}>
                  {count === 0
                    ? 'No documents uploaded'
                    : `${count} document${count === 1 ? '' : 's'}`}
                </Text>
              </View>
              <View style={[styles.badge, { backgroundColor: count > 0 ? Colors.indigo : Colors.border }]}>
                <Text style={styles.badgeText}>{count}</Text>
              </View>
            </TouchableOpacity>
          );
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header: {
    backgroundColor: Colors.navy,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 20,
  },
  headerTitle: { fontSize: 22, fontWeight: '800', color: '#fff' },
  headerSub:   { fontSize: 13, color: 'rgba(255,255,255,0.65)', marginTop: 4 },

  errorBanner: { backgroundColor: '#FEF2F2', padding: 12, marginHorizontal: 16, marginTop: 12, borderRadius: 10 },
  errorText:   { color: Colors.danger, fontSize: 13, fontWeight: '600' },

  list: { padding: 16, gap: 12 },

  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderLeftWidth: 4,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    ...Shadow.card,
  },
  iconWrap:  { width: 48, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  icon:      { fontSize: 24 },
  cardBody:  { flex: 1 },
  cardTitle: { fontSize: 16, fontWeight: '700', color: Colors.text },
  cardSub:   { fontSize: 12, color: Colors.muted, marginTop: 2 },

  badge: {
    minWidth: 28, height: 28, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6,
  },
  badgeText: { color: '#fff', fontSize: 13, fontWeight: '700' },
});

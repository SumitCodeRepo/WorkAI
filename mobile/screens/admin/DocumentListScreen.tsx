/**
 * screens/admin/DocumentListScreen.tsx
 * ---------------------------------------
 * PURPOSE:
 *   Shows all documents uploaded to a specific department.
 *   Admin can delete a document (with confirmation) and tap "Upload" to
 *   add a new one.
 *
 * CONCEPT — Alert.alert for Destructive Confirmations
 *   React Native's Alert.alert() is the idiomatic way to show native
 *   confirmation dialogs (uses UIAlertController on iOS, AlertDialog on Android).
 *   We use it for the delete confirmation so the user doesn't accidentally
 *   remove a document.
 *
 * CONCEPT — Polling after Deletion
 *   After deleting a document the backend rebuilds the FAISS index in the
 *   background. We don't wait for that — we just refetch the document list
 *   so the deleted item disappears from the UI immediately.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, FlatList, RefreshControl, SafeAreaView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';

import { adminApi, DocumentInfo } from '../../services/api';
import { Colors, Shadow } from '../../theme';
import { AdminStackParamList } from '../../App';

type Props = NativeStackScreenProps<AdminStackParamList, 'DocumentList'>;

export default function DocumentListScreen({ route, navigation }: Props) {
  const { department, departmentLabel } = route.params;

  const [documents,  setDocuments]  = useState<DocumentInfo[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error,      setError]      = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const res = await adminApi.listDocuments(department);
      setDocuments(res.data as DocumentInfo[]);
      setError(null);
    } catch {
      setError('Failed to load documents.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [department]);

  useEffect(() => {
    navigation.setOptions({ title: `${departmentLabel} Docs` });
    loadDocuments();
  }, [loadDocuments, navigation, departmentLabel]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    loadDocuments();
  }, [loadDocuments]);

  const confirmDelete = useCallback((doc: DocumentInfo) => {
    Alert.alert(
      'Delete Document',
      `Remove "${doc.filename}" from ${departmentLabel}? The FAISS index will be rebuilt automatically.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeletingId(doc.id);
            try {
              await adminApi.deleteDocument(doc.id);
              setDocuments(prev => prev.filter(d => d.id !== doc.id));
            } catch {
              Alert.alert('Error', 'Failed to delete document. Please try again.');
            } finally {
              setDeletingId(null);
            }
          },
        },
      ],
    );
  }, [departmentLabel]);

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
      {error && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <FlatList
        data={documents}
        keyExtractor={d => d.id.toString()}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.indigo} />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>📂</Text>
            <Text style={styles.emptyTitle}>No documents yet</Text>
            <Text style={styles.emptySub}>Upload a PDF, DOCX, or TXT file to build the knowledge base.</Text>
          </View>
        }
        renderItem={({ item: doc }) => (
          <View style={styles.card}>
            <View style={styles.cardIcon}>
              <Text style={styles.typeEmoji}>
                {doc.source_type === 'pdf' ? '📄' : doc.source_type === 'url' ? '🌐' : '📝'}
              </Text>
            </View>
            <View style={styles.cardBody}>
              <Text style={styles.filename} numberOfLines={1}>{doc.filename}</Text>
              <Text style={styles.meta}>
                {doc.chunk_count > 0
                  ? `${doc.chunk_count} chunks · ${doc.source_type.toUpperCase()}`
                  : 'Indexing…'}
              </Text>
              <Text style={styles.date}>
                {new Date(doc.uploaded_at).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })}
              </Text>
            </View>
            <TouchableOpacity
              style={[styles.deleteBtn, deletingId === doc.id && styles.deleteBtnDisabled]}
              onPress={() => confirmDelete(doc)}
              disabled={deletingId === doc.id}
            >
              {deletingId === doc.id
                ? <ActivityIndicator size="small" color={Colors.danger} />
                : <Text style={styles.deleteIcon}>🗑️</Text>}
            </TouchableOpacity>
          </View>
        )}
      />

      {/* Floating upload button */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => navigation.navigate('UploadDocument', { department, departmentLabel })}
        activeOpacity={0.85}
      >
        <Text style={styles.fabText}>+ Upload</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  errorBanner: { backgroundColor: '#FEF2F2', padding: 12, margin: 16, borderRadius: 10 },
  errorText:   { color: Colors.danger, fontSize: 13, fontWeight: '600' },

  list: { padding: 16, paddingBottom: 100, gap: 10 },

  empty: { alignItems: 'center', paddingTop: 80, paddingHorizontal: 32 },
  emptyIcon:  { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  emptySub:   { fontSize: 14, color: Colors.muted, textAlign: 'center', marginTop: 8, lineHeight: 22 },

  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    gap: 12,
    ...Shadow.card,
  },
  cardIcon: {
    width: 44, height: 44, borderRadius: 10,
    backgroundColor: Colors.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  typeEmoji: { fontSize: 22 },
  cardBody:  { flex: 1 },
  filename:  { fontSize: 14, fontWeight: '700', color: Colors.text },
  meta:      { fontSize: 12, color: Colors.muted, marginTop: 2 },
  date:      { fontSize: 11, color: Colors.placeholder, marginTop: 2 },

  deleteBtn: {
    width: 38, height: 38, borderRadius: 10,
    backgroundColor: '#FEF2F2',
    alignItems: 'center', justifyContent: 'center',
  },
  deleteBtnDisabled: { opacity: 0.5 },
  deleteIcon: { fontSize: 18 },

  fab: {
    position: 'absolute', bottom: 24, right: 20,
    backgroundColor: Colors.indigo,
    borderRadius: 28, paddingVertical: 14, paddingHorizontal: 24,
    ...Shadow.card,
  },
  fabText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});

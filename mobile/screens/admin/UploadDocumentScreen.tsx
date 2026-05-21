/**
 * screens/admin/UploadDocumentScreen.tsx
 * ----------------------------------------
 * PURPOSE:
 *   Lets an admin pick a file from the device and upload it to the backend
 *   for ingestion into the department's FAISS knowledge base.
 *
 * CONCEPT — expo-document-picker
 *   expo-document-picker wraps the native file picker on iOS (UIDocumentPicker)
 *   and Android (Android Storage Access Framework). It returns a `uri` — a local
 *   file path — that we attach to a FormData object.
 *
 *   Result shape (v54+):
 *     { canceled: boolean, assets: [{ uri, name, mimeType, size }] | null }
 *
 * CONCEPT — FormData for multipart/form-data upload
 *   HTTP file uploads use multipart/form-data encoding. We create a FormData
 *   object, append the file (uri + name + type) and the department string,
 *   then POST it with Content-Type: multipart/form-data.
 *
 *   Axios serialises the FormData automatically on React Native — the native
 *   HTTP stack handles the multipart encoding.
 *
 * CONCEPT — Upload Progress
 *   Axios fires `onUploadProgress` callbacks while sending the request body.
 *   We use this to drive a simple progress bar so the admin knows the upload
 *   is proceeding (large PDFs can take a few seconds on a slow connection).
 *
 * CONCEPT — 202 Accepted + polling
 *   The backend returns 202 immediately — ingestion (parse→chunk→embed→FAISS)
 *   runs as a background task. We show a "processing" message and tell the
 *   admin to check the document list to confirm when chunks appear.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator, Alert, SafeAreaView, ScrollView,
  StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { NativeStackScreenProps } from '@react-navigation/native-stack';

import { adminApi } from '../../services/api';
import { Colors, Shadow } from '../../theme';
import { AdminStackParamList } from '../../App';

type Props = NativeStackScreenProps<AdminStackParamList, 'UploadDocument'>;

// MIME types accepted by the picker — matching backend ALLOWED_EXTENSIONS.
const ACCEPTED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
];

type UploadState = 'idle' | 'uploading' | 'success' | 'error';

interface PickedFile {
  uri:      string;
  name:     string;
  mimeType: string;
  size:     number;
}

export default function UploadDocumentScreen({ route, navigation }: Props) {
  const { department, departmentLabel } = route.params;

  const [file,     setFile]     = useState<PickedFile | null>(null);
  const [state,    setState]    = useState<UploadState>('idle');
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  const pickFile = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type:                 ACCEPTED_TYPES,
        copyToCacheDirectory: true,
        multiple:             false,
      });

      if (result.canceled || !result.assets?.length) return;

      const asset = result.assets[0];
      setFile({
        uri:      asset.uri,
        name:     asset.name ?? 'upload',
        mimeType: asset.mimeType ?? 'application/octet-stream',
        size:     asset.size ?? 0,
      });
      setState('idle');
    } catch {
      Alert.alert('Error', 'Could not open the file picker. Please try again.');
    }
  }, []);

  const handleUpload = useCallback(async () => {
    if (!file) return;

    setState('uploading');
    setProgress(0);

    const formData = new FormData();
    formData.append('department', department);
    formData.append('file', {
      uri:  file.uri,
      name: file.name,
      type: file.mimeType,
    } as unknown as Blob);

    try {
      await adminApi.uploadDocument(formData, setProgress);
      setState('success');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Upload failed. Please try again.';
      setErrorMsg(detail);
      setState('error');
    }
  }, [file, department]);

  const reset = useCallback(() => {
    setFile(null);
    setState('idle');
    setProgress(0);
    setErrorMsg('');
  }, []);

  // ── Success state ──────────────────────────────────────────────────────────
  if (state === 'success') {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.resultCard}>
          <Text style={styles.resultIcon}>✅</Text>
          <Text style={styles.resultTitle}>Upload Queued!</Text>
          <Text style={styles.resultBody}>
            <Text style={{ fontWeight: '700' }}>{file?.name}</Text>
            {' '}has been sent to the backend.{'\n\n'}
            Indexing runs in the background — check the document list in a few seconds
            to confirm chunks have been created.
          </Text>
          <TouchableOpacity style={styles.btn} onPress={() => navigation.goBack()}>
            <Text style={styles.btnText}>Back to Document List</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnOutline} onPress={reset}>
            <Text style={styles.btnOutlineText}>Upload Another</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Main upload UI ─────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>

        {/* Department context */}
        <View style={styles.deptBadge}>
          <Text style={styles.deptBadgeText}>📁 {departmentLabel}</Text>
        </View>

        <Text style={styles.heading}>Upload Policy Document</Text>
        <Text style={styles.subheading}>
          Supported formats: PDF, DOCX, TXT, MD
        </Text>

        {/* File picker area */}
        <TouchableOpacity
          style={[styles.dropZone, file && styles.dropZoneSelected]}
          onPress={pickFile}
          activeOpacity={0.8}
          disabled={state === 'uploading'}
        >
          {file ? (
            <>
              <Text style={styles.fileIcon}>📄</Text>
              <Text style={styles.fileName}>{file.name}</Text>
              <Text style={styles.fileSize}>
                {(file.size / 1024).toFixed(1)} KB · Tap to change
              </Text>
            </>
          ) : (
            <>
              <Text style={styles.dropIcon}>⬆️</Text>
              <Text style={styles.dropTitle}>Tap to pick a file</Text>
              <Text style={styles.dropSub}>PDF, DOCX, TXT, or MD</Text>
            </>
          )}
        </TouchableOpacity>

        {/* Upload progress */}
        {state === 'uploading' && (
          <View style={styles.progressWrap}>
            <View style={styles.progressBar}>
              <View style={[styles.progressFill, { width: `${progress}%` }]} />
            </View>
            <Text style={styles.progressLabel}>Uploading… {progress}%</Text>
          </View>
        )}

        {/* Error */}
        {state === 'error' && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>⚠️ {errorMsg}</Text>
          </View>
        )}

        {/* Upload button */}
        <TouchableOpacity
          style={[styles.uploadBtn, (!file || state === 'uploading') && styles.uploadBtnDisabled]}
          onPress={handleUpload}
          disabled={!file || state === 'uploading'}
          activeOpacity={0.8}
        >
          {state === 'uploading'
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.uploadBtnText}>Upload & Index</Text>}
        </TouchableOpacity>

        {/* Info box */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>What happens after upload?</Text>
          <Text style={styles.infoBody}>
            1. The file is saved on the server.{'\n'}
            2. Text is extracted and split into chunks.{'\n'}
            3. Each chunk is embedded (sentence-transformers).{'\n'}
            4. Embeddings are stored in the {departmentLabel} FAISS index.{'\n'}
            5. The agent can now answer questions grounded in this document.
          </Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  scroll: { padding: 20, paddingBottom: 48 },

  deptBadge: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.indigo + '20',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
    marginBottom: 16,
  },
  deptBadgeText: { color: Colors.indigo, fontWeight: '700', fontSize: 13 },

  heading:    { fontSize: 22, fontWeight: '800', color: Colors.text, marginBottom: 6 },
  subheading: { fontSize: 14, color: Colors.muted, marginBottom: 24 },

  dropZone: {
    borderWidth: 2,
    borderColor: Colors.border,
    borderStyle: 'dashed',
    borderRadius: 16,
    paddingVertical: 48,
    paddingHorizontal: 24,
    alignItems: 'center',
    backgroundColor: '#fff',
    marginBottom: 20,
  },
  dropZoneSelected: { borderColor: Colors.indigo, borderStyle: 'solid', backgroundColor: '#EEF2FF' },
  dropIcon:  { fontSize: 40, marginBottom: 12 },
  dropTitle: { fontSize: 16, fontWeight: '700', color: Colors.text },
  dropSub:   { fontSize: 13, color: Colors.muted, marginTop: 4 },
  fileIcon:  { fontSize: 40, marginBottom: 10 },
  fileName:  { fontSize: 15, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  fileSize:  { fontSize: 12, color: Colors.muted, marginTop: 4 },

  progressWrap: { marginBottom: 16 },
  progressBar:  {
    height: 8, backgroundColor: Colors.border, borderRadius: 4, overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: Colors.indigo, borderRadius: 4 },
  progressLabel: { fontSize: 12, color: Colors.muted, marginTop: 6, textAlign: 'center' },

  errorBox: {
    backgroundColor: '#FEF2F2', borderRadius: 10, padding: 14, marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },

  uploadBtn: {
    backgroundColor: Colors.indigo, borderRadius: 14,
    paddingVertical: 16, alignItems: 'center', marginBottom: 24,
  },
  uploadBtnDisabled: { backgroundColor: Colors.border },
  uploadBtnText:     { color: '#fff', fontSize: 16, fontWeight: '700' },

  infoBox: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16, ...Shadow.card,
  },
  infoTitle: { fontSize: 13, fontWeight: '700', color: Colors.text, marginBottom: 10 },
  infoBody:  { fontSize: 13, color: Colors.muted, lineHeight: 22 },

  // ── Success state ──
  resultCard: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  resultIcon:  { fontSize: 64, marginBottom: 16 },
  resultTitle: { fontSize: 24, fontWeight: '800', color: Colors.text, marginBottom: 12 },
  resultBody: {
    fontSize: 15, color: Colors.muted, textAlign: 'center', lineHeight: 24, marginBottom: 32,
  },
  btn: {
    backgroundColor: Colors.indigo, borderRadius: 14,
    paddingVertical: 14, paddingHorizontal: 32,
    width: '100%', alignItems: 'center', marginBottom: 12,
  },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  btnOutline: {
    borderWidth: 2, borderColor: Colors.indigo, borderRadius: 14,
    paddingVertical: 14, paddingHorizontal: 32,
    width: '100%', alignItems: 'center',
  },
  btnOutlineText: { color: Colors.indigo, fontSize: 16, fontWeight: '700' },
});

/**
 * screens/ChatScreen.tsx
 * ----------------------
 * PURPOSE:
 *   Full chat interface for a department agent. Handles:
 *     - Sending a user message
 *     - Streaming the AI response token by token via SSE
 *     - Showing a typing indicator before the first token arrives
 *     - Displaying the routing decision (which agent answered + confidence)
 *     - Handling the clarification flow (low-confidence routing)
 *     - Persisting the session_id across messages in the same conversation
 *
 * CONCEPT — Optimistic UI
 *   The user message is added to the list immediately when Send is tapped,
 *   before the API call even starts. This makes the app feel instantaneous.
 *   If the API fails, we show an error but keep the user message so they
 *   can see what they sent.
 *
 * CONCEPT — FlatList for Chat
 *   FlatList only renders items visible on screen (virtualised), making it
 *   efficient for long conversations. Key props:
 *     data              — array of messages
 *     renderItem        — renders each message bubble
 *     keyExtractor      — unique key per item (prevents re-render glitches)
 *     onContentSizeChange — auto-scroll to bottom when new content arrives
 *     ListFooterComponent — typing indicator rendered below all messages
 *
 * CONCEPT — Streaming State Machine
 *   The stream progresses through these states:
 *
 *     idle → [send] → routing → typing → streaming → done
 *                                             ↓
 *                                          clarify (if low confidence)
 *
 *   We model this with three boolean flags:
 *     isStreaming  — true from send until done/error
 *     isTyping     — true from routing until first token
 *     isClarify    — true when the router returns clarification_needed
 *
 * CONCEPT — useRef for mutable values
 *   Some values need to persist across renders but should NOT trigger
 *   re-renders when they change:
 *     abortStream  — the XHR abort function (clean up on unmount)
 *     sessionId    — set once from 'metadata' event, referenced in next send
 *   We use useRef() for these to avoid unnecessary renders.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList, KeyboardAvoidingView, Platform, SafeAreaView,
  StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';

import { useAuth } from '../context/AuthContext';
import { streamChatMessage, RoutingInfo } from '../services/chatService';
import MessageBubble, { ChatMessage } from '../components/MessageBubble';
import TypingIndicator from '../components/TypingIndicator';
import { Colors, Shadow } from '../theme';
import { MainStackParamList } from '../App';
import { DepartmentKey } from './HomeScreen';

type Props = NativeStackScreenProps<MainStackParamList, 'Chat'>;

// Per-department config for the header.
const DEPT_CONFIG: Record<DepartmentKey, { icon: string; color: string; bg: string }> = {
  hr:      { icon: '👥', color: Colors.hr.accent,      bg: Colors.hr.bg },
  it:      { icon: '💻', color: Colors.it.accent,      bg: Colors.it.bg },
  finance: { icon: '💰', color: Colors.finance.accent, bg: Colors.finance.bg },
  legal:   { icon: '⚖️', color: Colors.legal.accent,   bg: Colors.legal.bg },
  admin:   { icon: '📋', color: Colors.admin.accent,    bg: Colors.admin.bg },
};

const STREAMING_ID = '__streaming__';

export default function ChatScreen({ route, navigation }: Props) {
  const { department, departmentLabel } = route.params;
  const { token } = useAuth();
  const dept = DEPT_CONFIG[department];

  const [messages,    setMessages]    = useState<ChatMessage[]>([]);
  const [inputText,   setInputText]   = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isTyping,    setIsTyping]    = useState(false);
  const [clarifyInfo, setClarifyInfo] = useState<{ message: string; departments: string[] } | null>(null);

  // Refs: mutate without re-render.
  const sessionIdRef   = useRef<number | null>(null);
  const abortStreamRef = useRef<(() => void) | null>(null);
  const flatListRef    = useRef<FlatList<ChatMessage>>(null);

  // Abort the XHR if the user navigates away mid-stream.
  useEffect(() => () => { abortStreamRef.current?.(); }, []);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, []);

  // ── Send a message ──────────────────────────────────────────────────────────
  const handleSend = useCallback((overrideMessage?: string) => {
    const text = (overrideMessage ?? inputText).trim();
    if (!text || isStreaming || !token) return;

    setInputText('');
    setClarifyInfo(null);

    // 1. Add user message optimistically.
    const userMsg: ChatMessage = {
      id:        Date.now().toString(),
      role:      'user',
      content:   text,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);
    setIsStreaming(true);
    scrollToBottom();

    // Track current routing info so we can attach it to the assistant bubble.
    let currentRouting: RoutingInfo | null = null;

    // 2. Start SSE stream.
    abortStreamRef.current = streamChatMessage(
      text,
      token,
      sessionIdRef.current,
      {
        onRouting(info) {
          currentRouting = info;
          // Typing indicator stays on — first token will hide it.
        },

        onMetadata(sid) {
          // Store session_id for subsequent messages in this conversation.
          sessionIdRef.current = sid;
        },

        onToken(tok) {
          setIsTyping(false);

          setMessages(prev => {
            const existing = prev.find(m => m.id === STREAMING_ID);
            if (existing) {
              // Append token to the in-progress streaming bubble.
              return prev.map(m =>
                m.id === STREAMING_ID
                  ? { ...m, content: m.content + tok }
                  : m,
              );
            }
            // First token — create the streaming bubble.
            const streamingMsg: ChatMessage = {
              id:         STREAMING_ID,
              role:       'assistant',
              content:    tok,
              streaming:  true,
              routedTo:   currentRouting?.department === 'clarification_needed'
                            ? undefined
                            : (currentRouting?.department
                                ? `${departmentLabel} Agent`
                                : `${departmentLabel} Agent`),
              confidence: currentRouting?.confidence,
              timestamp:  new Date().toISOString(),
            };
            return [...prev, streamingMsg];
          });

          scrollToBottom();
        },

        onDone() {
          // Finalise the streaming bubble — remove cursor, lock it in place.
          setMessages(prev =>
            prev.map(m =>
              m.id === STREAMING_ID
                ? { ...m, id: Date.now().toString(), streaming: false }
                : m,
            ),
          );
          setIsStreaming(false);
          setIsTyping(false);
          scrollToBottom();
        },

        onClarify(message, departments) {
          // Remove typing indicator, show department picker instead.
          setIsTyping(false);
          setIsStreaming(false);

          // Add a clarification assistant message.
          const clarifyMsg: ChatMessage = {
            id:        Date.now().toString(),
            role:      'assistant',
            content:   message,
            routedTo:  'WorkAI',
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, clarifyMsg]);
          setClarifyInfo({ message, departments });
          scrollToBottom();
        },

        onError(detail) {
          setIsTyping(false);
          setIsStreaming(false);

          // Remove any partial streaming bubble.
          setMessages(prev => prev.filter(m => m.id !== STREAMING_ID));

          const errorMsg: ChatMessage = {
            id:        Date.now().toString(),
            role:      'assistant',
            content:   `⚠️ ${detail}`,
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, errorMsg]);
          scrollToBottom();
        },
      },
    );
  }, [inputText, isStreaming, token, departmentLabel, scrollToBottom]);

  // ── Clarification: user picks a department ──────────────────────────────────
  const handleClarify = useCallback((chosenDept: string) => {
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user');
    if (!lastUserMsg) return;
    setClarifyInfo(null);
    // Re-send with /chat/query using the chosen department (direct route).
    // For simplicity we navigate to a fresh chat for that department.
    navigation.replace('Chat', {
      department: chosenDept as DepartmentKey,
      departmentLabel: chosenDept.charAt(0).toUpperCase() + chosenDept.slice(1),
    });
  }, [messages, navigation]);

  // ── Render each message ─────────────────────────────────────────────────────
  const renderItem = useCallback(
    ({ item }: { item: ChatMessage }) => <MessageBubble message={item} />,
    [],
  );

  const keyExtractor = useCallback((item: ChatMessage) => item.id, []);

  return (
    <SafeAreaView style={styles.safe}>
      {/* ── Header ── */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>←</Text>
        </TouchableOpacity>

        <View style={styles.deptInfo}>
          <View style={[styles.deptIconWrap, { backgroundColor: dept.bg }]}>
            <Text style={styles.deptIcon}>{dept.icon}</Text>
          </View>
          <View>
            <Text style={styles.deptName}>{departmentLabel}</Text>
            <Text style={styles.deptSub}>Powered by WorkAI</Text>
          </View>
        </View>

        <View style={styles.agentBadge}>
          <View style={[styles.agentDot, isStreaming && styles.agentDotActive]} />
          <Text style={styles.agentBadgeText}>
            {isStreaming ? 'Responding…' : `${departmentLabel} Agent`}
          </Text>
        </View>
      </View>

      {/* ── Messages ── */}
      <FlatList
        ref={flatListRef}
        data={messages}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        contentContainerStyle={styles.messagesList}
        ListHeaderComponent={
          messages.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>{dept.icon}</Text>
              <Text style={styles.emptyTitle}>Ask the {departmentLabel} Agent</Text>
              <Text style={styles.emptyBody}>
                Ask any question about {departmentLabel.toLowerCase()} policies,
                procedures, or guidelines.
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          isTyping ? (
            <View style={styles.typingWrap}>
              <View style={styles.routingPillWarn}>
                <Text style={styles.routingPillText}>🎯 Routing…</Text>
              </View>
              <TypingIndicator />
            </View>
          ) : null
        }
        onContentSizeChange={scrollToBottom}
        showsVerticalScrollIndicator={false}
      />

      {/* ── Clarify department picker ── */}
      {clarifyInfo && (
        <View style={styles.clarifyBar}>
          <Text style={styles.clarifyLabel}>Which department can help?</Text>
          <View style={styles.clarifyChips}>
            {clarifyInfo.departments.map(d => (
              <TouchableOpacity
                key={d}
                style={styles.clarifyChip}
                onPress={() => handleClarify(d)}
              >
                <Text style={styles.clarifyChipText}>
                  {DEPT_CONFIG[d as DepartmentKey]?.icon ?? '🏢'}{' '}
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      {/* ── Input bar ── */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type your question…"
            placeholderTextColor={Colors.placeholder}
            multiline
            maxLength={1000}
            returnKeyType="send"
            blurOnSubmit={false}
            onSubmitEditing={() => handleSend()}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!inputText.trim() || isStreaming) && styles.sendBtnDisabled]}
            onPress={() => handleSend()}
            disabled={!inputText.trim() || isStreaming}
            activeOpacity={0.8}
          >
            <Text style={styles.sendIcon}>➤</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },

  // ── Header ──
  header: {
    backgroundColor: Colors.navy,
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  backBtn:  { width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  backText: { color: '#fff', fontSize: 18 },

  deptInfo:    { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10 },
  deptIconWrap:{ width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  deptIcon:    { fontSize: 18 },
  deptName:    { fontSize: 15, fontWeight: '700', color: '#fff' },
  deptSub:     { fontSize: 11, color: 'rgba(255,255,255,0.6)' },

  agentBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: 'rgba(99,102,241,0.25)',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.5)',
    borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4,
  },
  agentDot:       { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.muted },
  agentDotActive: { backgroundColor: Colors.success },
  agentBadgeText: { fontSize: 10, fontWeight: '600', color: '#A5B4FC' },

  // ── Messages ──
  messagesList: { padding: 16, paddingBottom: 8 },

  typingWrap: { marginBottom: 12 },

  routingPillWarn: {
    alignSelf: 'flex-start',
    backgroundColor: '#EEF2FF', borderWidth: 1, borderColor: '#C7D2FE',
    borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4, marginBottom: 6,
  },
  routingPillText: { fontSize: 11, fontWeight: '600', color: Colors.indigo },

  emptyState: { alignItems: 'center', paddingTop: 60, paddingBottom: 32, paddingHorizontal: 32 },
  emptyIcon:  { fontSize: 56, marginBottom: 16 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: Colors.text, textAlign: 'center' },
  emptyBody:  { fontSize: 14, color: Colors.muted, textAlign: 'center', marginTop: 8, lineHeight: 22 },

  // ── Clarify bar ──
  clarifyBar: {
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: Colors.border,
    padding: 12,
  },
  clarifyLabel: { fontSize: 12, fontWeight: '600', color: Colors.muted, marginBottom: 8 },
  clarifyChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  clarifyChip: {
    paddingVertical: 8, paddingHorizontal: 14,
    backgroundColor: Colors.bg, borderWidth: 1.5, borderColor: Colors.border,
    borderRadius: 20,
  },
  clarifyChipText: { fontSize: 13, fontWeight: '600', color: Colors.text },

  // ── Input bar ──
  inputBar: {
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: Colors.border,
    flexDirection: 'row', alignItems: 'flex-end', gap: 10,
    paddingHorizontal: 16, paddingTop: 10, paddingBottom: Platform.OS === 'ios' ? 24 : 12,
  },
  input: {
    flex: 1, backgroundColor: Colors.bg, borderWidth: 1.5, borderColor: Colors.border,
    borderRadius: 24, paddingHorizontal: 16, paddingVertical: 10,
    fontSize: 15, color: Colors.text, maxHeight: 100,
  },
  sendBtn:         { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.indigo, alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { backgroundColor: Colors.border },
  sendIcon:        { color: '#fff', fontSize: 18 },
});

/**
 * components/MessageBubble.tsx
 * -----------------------------
 * PURPOSE:
 *   Renders a single chat message — either a user bubble (right, indigo)
 *   or an assistant bubble (left, white) with an optional routing pill
 *   and a blinking cursor while the message is still streaming.
 *
 * CONCEPT — Memoisation with React.memo
 *   In a chat list with many messages, every state change (e.g. a new token
 *   arrives) re-renders the parent. Without memoisation, every MessageBubble
 *   in the list re-renders even though only the last one changed.
 *
 *   React.memo wraps a component and skips re-renders when props are
 *   reference-equal. For a 50-message chat thread this cuts re-renders
 *   from 50 to 1 on each token, keeping the UI smooth at 60fps.
 *
 *   The streaming message (id='streaming') is explicitly excluded from
 *   memoisation because its content changes on every token.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Shadow } from '../theme';

export interface ChatMessage {
  id:         string;
  role:       'user' | 'assistant';
  content:    string;
  streaming?: boolean;   // true while tokens are still arriving
  routedTo?:  string;    // department name, shown in routing pill
  confidence?: number;
  timestamp:  string;    // ISO string
}

interface Props {
  message: ChatMessage;
}

function MessageBubble({ message }: Props) {
  const isUser      = message.role === 'user';
  const timeLabel   = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit',
  });

  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      {/* Routing pill — shown above the first assistant response */}
      {!isUser && message.routedTo && (
        <View style={styles.routingPill}>
          <Text style={styles.routingText}>
            🎯 {message.routedTo}
            {message.confidence != null
              ? ` · ${Math.round(message.confidence * 100)}% confidence`
              : ''}
          </Text>
        </View>
      )}

      {/* Message bubble */}
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
        <Text style={[styles.content, isUser ? styles.contentUser : styles.contentAssistant]}>
          {message.content}
          {/* Blinking cursor while streaming */}
          {message.streaming && <Text style={styles.cursor}>▋</Text>}
        </Text>
      </View>

      {/* Timestamp */}
      <Text style={styles.time}>
        {timeLabel}{!isUser && message.routedTo ? ` · ${message.routedTo}` : ''}
      </Text>
    </View>
  );
}

// Skip re-render for all messages except the one currently streaming.
export default React.memo(MessageBubble, (prev, next) => {
  if (next.message.streaming) return false;   // always re-render streaming bubble
  return prev.message.content === next.message.content;
});

const styles = StyleSheet.create({
  row: {
    maxWidth: '82%',
    marginBottom: 12,
  },
  rowUser:      { alignSelf: 'flex-end',   alignItems: 'flex-end' },
  rowAssistant: { alignSelf: 'flex-start', alignItems: 'flex-start' },

  routingPill: {
    backgroundColor: '#EEF2FF',
    borderWidth: 1,
    borderColor: '#C7D2FE',
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginBottom: 6,
  },
  routingText: {
    fontSize: 11,
    fontWeight: '600',
    color: Colors.indigo,
  },

  bubble: {
    borderRadius: 18,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  bubbleUser: {
    backgroundColor: Colors.indigo,
    borderBottomRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: '#fff',
    borderBottomLeftRadius: 4,
    ...Shadow.card,
  },

  content: {
    fontSize: 15,
    lineHeight: 22,
  },
  contentUser:      { color: '#fff' },
  contentAssistant: { color: Colors.text },

  cursor: {
    color: Colors.indigo,
    opacity: 0.8,
  },

  time: {
    fontSize: 10,
    color: Colors.muted,
    marginTop: 4,
    paddingHorizontal: 4,
  },
});

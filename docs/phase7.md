# Phase 7 — Chat UI (Home + Chat Screens)

## Concepts Learned

### FlatList for Chat
`FlatList` is React Native's virtualised list component — it only renders items
currently visible on screen, making it memory-efficient for long chat histories.

Key props used:
| Prop | Purpose |
|---|---|
| `data` | Array of `ChatMessage` objects |
| `renderItem` | Renders each message bubble |
| `keyExtractor` | Unique key per item — prevents re-render glitches |
| `ListHeaderComponent` | Empty-state illustration when no messages |
| `ListFooterComponent` | Typing indicator rendered below all messages |
| `onContentSizeChange` | Auto-scroll to bottom when new content arrives |
| `ref` | Allows imperative `scrollToEnd()` call |

### SSE Streaming in React Native
The browser's `EventSource` API is not available in React Native. Instead, we use
`XMLHttpRequest` with its `onprogress` callback, which fires each time new bytes
arrive from the server.

**Byte offset tracking:** Each `onprogress` call gives the full `responseText`
from the beginning of the response. We track a `offset` integer and slice from
it to get only the new bytes, avoiding reprocessing already-parsed data.

**Buffer for partial events:** SSE events are separated by `\n\n`. A single
`onprogress` chunk may arrive in the middle of an event. We keep an incomplete
fragment in `buffer` and prepend it to the next chunk.

```typescript
xhr.onprogress = () => {
  const newText = xhr.responseText.slice(offset);
  offset = xhr.responseText.length;
  buffer += newText;
  const parts = buffer.split('\n\n');
  buffer = parts.pop() ?? '';    // last element may be incomplete
  for (const block of parts) { /* parse + dispatch */ }
};
```

### Optimistic UI
The user message is appended to the list **immediately** when the Send button is
tapped, before the API call completes. This makes the app feel instantaneous.
If the server returns an error, the error message is shown but the user message
is kept so the user can see what they sent.

### Streaming State Machine
The stream progresses through these states:

```
idle → [send] → typing → streaming → done
                              ↓
                           clarify (if confidence < 0.50)
```

Three boolean flags model this:
- `isStreaming` — true from send until done/error
- `isTyping` — true until the first token arrives
- `clarifyInfo` — set when the router returns `clarification_needed`

### STREAMING_ID Sentinel
While tokens are arriving, the in-progress bubble has a fixed ID `'__streaming__'`.
This allows the `onToken` callback to find and update the right bubble with a
functional `setMessages` update. When `onDone` fires, the ID is replaced with
`Date.now().toString()` and `streaming: false` is set, locking the bubble in place.

### React.memo with Custom Comparator
Wrapping `MessageBubble` in `React.memo` skips re-renders when props are
reference-equal. We provide a custom comparator:

```typescript
React.memo(MessageBubble, (prev, next) => {
  if (next.message.streaming) return false;  // always re-render streaming bubble
  return prev.message.content === next.message.content;
});
```

For a 50-message conversation, this cuts re-renders from 50→1 on each token.

### Animated API for Typing Indicator
React Native's `Animated` library drives animations on the native thread via
`useNativeDriver: true`, bypassing the JS bridge for smooth 60fps:

```typescript
Animated.loop(
  Animated.stagger(150, dots.map(bounce))  // each dot starts 150ms after the last
).start();
```

`bounce` is a sequence: move up 8px (300ms) → return to 0 (300ms) → pause (100ms).

### useRef for Mutable Values
Some values need to persist across renders but should NOT trigger re-renders:
- `sessionIdRef` — session ID received from `metadata` SSE event; referenced in next send
- `abortStreamRef` — XHR abort function; called on component unmount to prevent memory leaks
- `flatListRef` — imperative reference to the FlatList for `scrollToEnd()`

---

## What Was Built

### `mobile/services/chatService.ts`
XHR-based SSE streaming service. Exports:
- `streamChatMessage(message, authToken, sessionId, callbacks) → () => void`
  - Returns an abort function to cancel the stream on unmount
- `RoutingInfo` type: `{ department, confidence, reason }`
- `StreamCallbacks` interface: `onRouting | onMetadata | onToken | onDone | onClarify | onError`

SSE event types handled:
| Event | Data | Callback |
|---|---|---|
| `routing` | `{ department, confidence, reason }` | `onRouting(info)` |
| `metadata` | `{ session_id, department }` | `onMetadata(sid, dept)` |
| `token` | raw text (newlines escaped as `\\n`) | `onToken(text)` |
| `done` | `{}` | `onDone()` |
| `clarify` | `{ message, departments[] }` | `onClarify(msg, depts)` |
| `error` | `{ detail }` | `onError(detail)` |

Token newline unescaping: `rawData.replace(/\\n/g, '\n')` — the backend escapes
newlines inside SSE `data:` lines to keep each event on a single line.

### `mobile/components/TypingIndicator.tsx`
Three animated dots shown while the LLM is generating the first token.
- Uses `Animated.Value`, `Animated.timing`, `Animated.loop`, `Animated.stagger`
- `useNativeDriver: true` — runs on native thread for 60fps
- Matches the assistant bubble style (white, rounded, shadow)

### `mobile/components/MessageBubble.tsx`
Renders a single chat message. Exported types:
```typescript
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;   // true while tokens are still arriving
  routedTo?: string;     // shown in routing pill
  confidence?: number;   // shown as percentage in routing pill
  timestamp: string;     // ISO string
}
```

Visual features:
- **User bubble**: right-aligned, indigo background, white text
- **Assistant bubble**: left-aligned, white background, shadow
- **Routing pill**: shows which agent answered + confidence %
- **Blinking cursor**: `▋` appended while `streaming === true`
- **Timestamp**: below the bubble; includes `routedTo` for assistant messages

### `mobile/screens/ChatScreen.tsx`
Full chat interface. Features:
- Header with department icon, name, "Powered by WorkAI", and live agent badge
  (dot pulses green while streaming)
- `FlatList` with empty-state illustration when no messages
- Typing indicator (routing pill + animated dots) while waiting for first token
- Clarification bar with department chips when router confidence is low
- `KeyboardAvoidingView` around input bar
- Multiline `TextInput` (max 100px height) with Send button
- Back button navigates to Home

Clarification flow:
1. Router returns `clarify` event with `{ message, departments }`
2. Assistant bubble added with the clarification message
3. Department chips appear above the input bar
4. User taps a chip → `navigation.replace('Chat', { department: chosenDept })`
   (replace so back button goes to Home, not the clarify state)

### `mobile/App.tsx` (updated)
Added `ChatScreen` import and screen registration in `MainNavigator`:
```tsx
<MainStack.Screen name="Chat" component={ChatScreen}
  options={{ headerShown: false }} />
```
`headerShown: false` because ChatScreen renders its own custom header with the
department colour, icon, and agent badge.

---

## File Checklist

| File | Status |
|---|---|
| `mobile/services/chatService.ts` | ✅ New |
| `mobile/components/TypingIndicator.tsx` | ✅ New |
| `mobile/components/MessageBubble.tsx` | ✅ New |
| `mobile/screens/ChatScreen.tsx` | ✅ New |
| `mobile/App.tsx` | ✅ Updated |

**TypeScript:** `npx tsc --noEmit` → 0 errors.

---

## How to Test

1. Start the backend: `cd backend && ..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000`
2. Start Expo: `cd mobile && npx expo start`
3. Open Expo Go on device or press `a` for Android emulator
4. Log in → tap any department card → type a question → watch tokens stream in
5. Verify:
   - Typing indicator (animated dots + "Routing…" pill) appears while waiting
   - Tokens stream one by one into the assistant bubble
   - Routing pill shows department name + confidence % on the first assistant message
   - User message appears immediately (optimistic UI)
   - On low-confidence queries, clarification chips appear
   - Navigating away mid-stream aborts the XHR

---

## Next Phase
**Phase 8 — Admin Panel UI**
- Admin tab (visible only for `role === 'admin'`)
- `DocumentListScreen` — list + delete documents per department
- `UploadDocumentScreen` — native file picker + FormData multipart upload
- Upload progress indicator

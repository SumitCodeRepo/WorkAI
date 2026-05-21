/**
 * services/chatService.ts
 * -----------------------
 * PURPOSE:
 *   Handles the SSE (Server-Sent Events) streaming connection to
 *   POST /chat/message. Parses each event type and fires typed callbacks
 *   so ChatScreen stays focused on UI logic, not protocol details.
 *
 * CONCEPT — Why SSE instead of regular fetch?
 *   A regular fetch call waits for the entire response before giving you
 *   anything. SSE is a one-way streaming protocol where the server sends
 *   data progressively as it becomes available — ideal for LLM token streaming.
 *
 *   The backend sends events in this format:
 *       event: routing
 *       data: {"department": "hr", "confidence": 0.99, "reason": "..."}
 *
 *       event: token
 *       data: Based on the HR policy
 *
 *       event: done
 *       data: {}
 *
 *   Each event is separated by a blank line (\n\n).
 *
 * CONCEPT — Why XMLHttpRequest instead of the browser's EventSource?
 *   React Native does not implement the browser's EventSource API.
 *   XMLHttpRequest has an `onprogress` callback that fires each time new
 *   bytes arrive — we can use it to read the stream incrementally.
 *
 *   We track a byte offset so each `onprogress` call only processes
 *   the NEW bytes, not the entire response text from the beginning.
 *
 * CONCEPT — Buffering
 *   A single `onprogress` chunk may contain:
 *     - A complete event ("event: token\ndata: hello\n\n")
 *     - Multiple events ("event: token\ndata: hi\n\nevent: done\ndata: {}\n\n")
 *     - A partial event (chunk cut mid-stream)
 *
 *   We split on "\n\n" (the SSE event separator) and keep any trailing
 *   incomplete fragment in a buffer for the next chunk to complete.
 *
 * EXPORTS:
 *   streamChatMessage(...)  → starts stream, returns abort() function
 *   RoutingInfo             → type for the routing SSE event
 *   StreamCallbacks         → all callback types
 */

import { BASE_URL } from './api';

// ── Types ────────────────────────────────────────────────────────────────────
export interface RoutingInfo {
  department:  string;
  confidence:  number;
  reason:      string;
}

export interface StreamCallbacks {
  onRouting:  (info: RoutingInfo) => void;
  onMetadata: (sessionId: number, department: string) => void;
  onToken:    (token: string) => void;
  onDone:     () => void;
  onClarify:  (message: string, departments: string[]) => void;
  onError:    (detail: string) => void;
}

// ── SSE block parser ─────────────────────────────────────────────────────────
function parseBlock(block: string): { event: string; data: string } | null {
  let event = '';
  let data  = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    else if (line.startsWith('data: ')) data  = line.slice(6);
  }
  return event && data ? { event, data } : null;
}

function dispatchEvent(
  event: string,
  rawData: string,
  cb: StreamCallbacks,
): void {
  try {
    switch (event) {
      case 'routing': {
        const d = JSON.parse(rawData) as RoutingInfo;
        cb.onRouting(d);
        break;
      }
      case 'metadata': {
        const d = JSON.parse(rawData) as { session_id: number; department: string };
        cb.onMetadata(d.session_id, d.department);
        break;
      }
      case 'token': {
        // Backend escapes newlines as \\n inside SSE data lines — unescape them.
        cb.onToken(rawData.replace(/\\n/g, '\n'));
        break;
      }
      case 'done': {
        cb.onDone();
        break;
      }
      case 'clarify': {
        const d = JSON.parse(rawData) as { message: string; departments: string[] };
        cb.onClarify(d.message, d.departments);
        break;
      }
      case 'error': {
        const d = JSON.parse(rawData) as { detail: string };
        cb.onError(d.detail);
        break;
      }
    }
  } catch (err) {
    console.warn('[chatService] Failed to parse event:', event, rawData, err);
  }
}

// ── Main streaming function ───────────────────────────────────────────────────
/**
 * Opens an SSE stream to POST /chat/message.
 *
 * @param message    The user's question.
 * @param authToken  JWT token (from AuthContext).
 * @param sessionId  Existing session ID, or null for a new session.
 * @param callbacks  Event handlers for each SSE event type.
 * @returns          A function that aborts the stream when called.
 */
export function streamChatMessage(
  message:   string,
  authToken: string,
  sessionId: number | null,
  callbacks: StreamCallbacks,
): () => void {
  const xhr    = new XMLHttpRequest();
  let   offset = 0;        // bytes of xhr.responseText already processed
  let   buffer = '';       // incomplete SSE event fragment

  xhr.open('POST', `${BASE_URL}/chat/message`, true);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);

  // Fire on each new chunk of data.
  xhr.onprogress = () => {
    const newText = xhr.responseText.slice(offset);
    offset = xhr.responseText.length;

    buffer += newText;

    // Split on the SSE event separator (\n\n).
    // The last element may be an incomplete event — keep it in the buffer.
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const block of parts) {
      const parsed = parseBlock(block);
      if (parsed) dispatchEvent(parsed.event, parsed.data, callbacks);
    }
  };

  xhr.onerror = () => {
    callbacks.onError('Network error — check your connection.');
  };

  xhr.ontimeout = () => {
    callbacks.onError('Request timed out. The server may be busy.');
  };

  xhr.timeout = 60_000; // 60 s — LLM can be slow on a local machine

  xhr.send(JSON.stringify({ message, session_id: sessionId }));

  // Return an abort function so ChatScreen can cancel on unmount.
  return () => xhr.abort();
}

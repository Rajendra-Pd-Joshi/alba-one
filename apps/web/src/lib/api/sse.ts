/**
 * Streaming SSE Client with Backoff, Deduplication & Polling Fallback (`apps/web/src/lib/api/sse.ts`)
 *
 * Per Phase 8 User Answer 3:
 * - Uses `fetch` with a streaming `ReadableStreamDefaultReader` over `/api/proxy/v1/decisions/${decisionId}/events`
 *   (never puts tokens in query strings!).
 * - Aborts on unmount (`AbortController`), reconnects with exponential backoff and `Last-Event-ID`,
 *   de-duplicates events by `event_id`, logs and ignores unknown `event_type` values without crashing,
 *   exposes connection state (`"connecting" | "connected" | "reconnecting" | "polling_fallback"`),
 *   and automatically falls back to polling `GET /api/v1/decisions/{id}` if the stream fails repeatedly.
 */

import { fetchDecision } from "./api";
import type { DecisionRecord, DecisionSSEEvent } from "./schema";

export type SSEConnectionState = "connecting" | "connected" | "reconnecting" | "polling_fallback";

const KNOWN_EVENT_TYPES = new Set(["state_changed", "outbox_resumed", "guardrail_alert"]);

export function parseAndValidateSSEFrame(
  rawJson: string,
  seenEventIds: Set<string>
): DecisionSSEEvent | null {
  try {
    const parsed = JSON.parse(rawJson) as Record<string, unknown>;
    if (parsed.schema_version !== "1.0" || typeof parsed.event_id !== "string") {
      return null;
    }
    if (seenEventIds.has(parsed.event_id)) {
      return null; // Deduplicated by event_id
    }
    const eventType = String(parsed.event_type ?? "");
    if (!KNOWN_EVENT_TYPES.has(eventType)) {
      console.warn(`[ALBA SSE] Ignoring unknown event_type '${eventType}'`);
      return null;
    }
    seenEventIds.add(parsed.event_id);
    return parsed as unknown as DecisionSSEEvent;
  } catch {
    return null;
  }
}

export function subscribeToDecisionEvents(options: {
  decisionId: string;
  onEvent: (event: DecisionSSEEvent) => void;
  onPollSnapshot?: (record: DecisionRecord) => void;
  onStateChange: (state: SSEConnectionState) => void;
  maxStreamRetries?: number;
  pollIntervalMs?: number;
}): () => void {
  const {
    decisionId,
    onEvent,
    onPollSnapshot,
    onStateChange,
    maxStreamRetries = 3,
    pollIntervalMs = 3000,
  } = options;

  const controller = new AbortController();
  const seenEventIds = new Set<string>();
  let lastEventId = "";
  let retryCount = 0;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const startPollingFallback = () => {
    onStateChange("polling_fallback");
    pollTimer = setInterval(async () => {
      if (controller.signal.aborted) return;
      try {
        const snapshot = await fetchDecision(decisionId);
        onPollSnapshot?.(snapshot);
      } catch {
        // Keep polling until unmount
      }
    }, pollIntervalMs);
  };

  const connectStream = async () => {
    if (controller.signal.aborted) return;
    onStateChange(retryCount === 0 ? "connecting" : "reconnecting");

    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      if (lastEventId) {
        headers["Last-Event-ID"] = lastEventId;
      }
      const res = await fetch(`/api/proxy/v1/decisions/${encodeURIComponent(decisionId)}/events`, {
        method: "GET",
        headers,
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`SSE stream returned HTTP ${res.status}`);
      }
      onStateChange("connected");
      retryCount = 0;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          for (const line of frame.split("\n")) {
            if (line.startsWith("id:")) {
              lastEventId = line.slice(3).trim();
            } else if (line.startsWith("data:")) {
              const ev = parseAndValidateSSEFrame(line.slice(5).trim(), seenEventIds);
              if (ev) {
                lastEventId = ev.event_id;
                onEvent(ev);
              }
            }
          }
        }
      }
    } catch {
      if (controller.signal.aborted) return;
      retryCount += 1;
      if (retryCount > maxStreamRetries) {
        startPollingFallback();
        return;
      }
      const backoffMs = Math.min(8000, 500 * Math.pow(2, retryCount - 1));
      setTimeout(connectStream, backoffMs);
    }
  };

  void connectStream();

  return () => {
    controller.abort();
    if (pollTimer) {
      clearInterval(pollTimer);
    }
  };
}

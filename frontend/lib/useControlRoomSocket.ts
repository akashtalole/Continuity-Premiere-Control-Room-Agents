"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentEvent } from "./types";

export type SocketStatus = "connecting" | "open" | "closed";

export function useControlRoomSocket(url: string) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const reconnectAttempt = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let heartbeat: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      ws = new WebSocket(url);

      ws.onopen = () => {
        reconnectAttempt.current = 0;
        setStatus("open");
        heartbeat = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
        }, 15000);
      };

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as AgentEvent;
          setEvents((prev) => [...prev, event]);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setStatus("closed");
        if (heartbeat) clearInterval(heartbeat);
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 15000);
        reconnectAttempt.current += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (heartbeat) clearInterval(heartbeat);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [url]);

  return { events, status };
}

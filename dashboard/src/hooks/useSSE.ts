import { useEffect, useRef, useState } from "react";
import type { SSEHealth } from "../api/types";

export function useSSE(): SSEHealth | null {
  const [data, setData] = useState<SSEHealth | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function connect() {
      if (!mountedRef.current) return;
      const key = localStorage.getItem("recall_api_key");
      const url = key ? `/events/stream?token=${key}` : "/events/stream";
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("health", (e) => {
        try {
          setData(JSON.parse(e.data));
        } catch {}
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        // Reconnect after 5s
        setTimeout(connect, 5000);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  return data;
}

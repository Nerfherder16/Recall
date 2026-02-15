import { useEffect, useRef, useState } from "react";
import type { SSEHealth } from "../api/types";

export function useSSE(): SSEHealth | null {
  const [data, setData] = useState<SSEHealth | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
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
      // Reconnect after 5s
      setTimeout(() => {
        if (esRef.current === es) {
          esRef.current = null;
        }
      }, 5000);
    };

    return () => es.close();
  }, []);

  return data;
}

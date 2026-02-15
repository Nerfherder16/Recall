import { useCallback, useState } from "react";

export function useAuth() {
  const [apiKey, setApiKeyState] = useState(
    () => localStorage.getItem("recall_api_key") || "",
  );

  const setApiKey = useCallback((key: string) => {
    if (key) {
      localStorage.setItem("recall_api_key", key);
    } else {
      localStorage.removeItem("recall_api_key");
    }
    setApiKeyState(key);
  }, []);

  return { apiKey, setApiKey, isAuthenticated: !!apiKey };
}

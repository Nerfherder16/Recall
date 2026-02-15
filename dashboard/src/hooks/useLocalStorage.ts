import { useState, useCallback } from "react";

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored ? JSON.parse(stored) : initial;
    } catch {
      return initial;
    }
  });

  const set = useCallback((v: T) => {
    setValue(v);
    localStorage.setItem(key, JSON.stringify(v));
  }, [key]);

  return [value, set];
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ToastType = "success" | "error";
export type ShowToast = (t: ToastType, m: string) => void;

export function useToast() {
  const [message, setMessage] = useState<{ type: ToastType; text: string } | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((type: ToastType, text: string) => {
    setMessage({ type, text });
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setMessage(null), 2800);
  }, []);

  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    },
    [],
  );

  return { message, show };
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SystemFeedback } from "@/components/ui/SystemFeedback";
import { subscribeToSystemFeedback, type SystemFeedbackMessage } from "@/lib/systemFeedback";

export function SystemFeedbackToaster() {
  const [messages, setMessages] = useState<SystemFeedbackMessage[]>([]);
  const timers = useRef(new Map<string, number>());

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timers.current.delete(id);
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);

  useEffect(() => {
    const activeTimers = timers.current;
    const unsubscribe = subscribeToSystemFeedback((message) => {
      setMessages((current) => [...current.slice(-3), message]);
      const timeout = message.tone === "danger" ? 12_000 : 7_000;
      const timer = window.setTimeout(() => dismiss(message.id), timeout);
      activeTimers.set(message.id, timer);
    });
    return () => {
      unsubscribe();
      activeTimers.forEach((timer) => window.clearTimeout(timer));
      activeTimers.clear();
    };
  }, [dismiss]);

  return <div aria-label="System feedback" className="pointer-events-none fixed inset-x-0 top-3 z-[100] flex flex-col items-end gap-3 px-3 sm:inset-x-auto sm:right-4 sm:w-[min(26rem,calc(100vw-2rem))] sm:px-0">
    {messages.map((message) => <div key={message.id} className="pointer-events-auto w-full">
      <SystemFeedback
        className="shadow-xl"
        tone={message.tone}
        title={message.title}
        description={message.description}
        action={<button type="button" className="interactive-link text-sm font-medium underline" onClick={() => dismiss(message.id)}>Dismiss</button>}
      />
    </div>)}
  </div>;
}
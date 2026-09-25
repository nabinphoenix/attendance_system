import type { FeedbackTone } from "@/components/ui/SystemFeedback";

export type SystemFeedbackMessage = {
  id: string;
  tone: FeedbackTone;
  title: string;
  description?: string;
};

type FeedbackInput = Omit<SystemFeedbackMessage, "id">;

const eventName = "antimbench:system-feedback";
let messageSequence = 0;
let subscriberCount = 0;
let pendingMessages: SystemFeedbackMessage[] = [];
const recentMessages = new Map<string, number>();

export function notifySystemFeedback(message: FeedbackInput) {
  if (typeof window === "undefined") return;
  const now = Date.now();
  const signature = [message.tone, message.title, message.description || ""].join("\u0000");
  const lastSent = recentMessages.get(signature);
  if (lastSent !== undefined && now - lastSent < 1000) return;
  recentMessages.set(signature, now);
  recentMessages.forEach((sentAt, key) => {
    if (now - sentAt >= 10_000) recentMessages.delete(key);
  });
  const detail: SystemFeedbackMessage = {
    ...message,
    id: String(now) + "-" + String(++messageSequence),
  };
  if (subscriberCount === 0) {
    pendingMessages = [...pendingMessages.slice(-9), detail];
  }
  window.dispatchEvent(new CustomEvent<SystemFeedbackMessage>(eventName, { detail }));
}

export function subscribeToSystemFeedback(
  listener: (message: SystemFeedbackMessage) => void,
) {
  const handleEvent = (event: Event) => {
    const detail = (event as CustomEvent<SystemFeedbackMessage>).detail;
    if (detail && typeof detail.title === "string" && typeof detail.id === "string") {
      listener(detail);
    }
  };
  window.addEventListener(eventName, handleEvent);
  subscriberCount += 1;
  if (subscriberCount === 1 && pendingMessages.length) {
    const queued = pendingMessages;
    pendingMessages = [];
    queued.forEach(listener);
  }
  return () => {
    window.removeEventListener(eventName, handleEvent);
    subscriberCount = Math.max(0, subscriberCount - 1);
  };
}

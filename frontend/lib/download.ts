import api from "./api";
import { isAxiosError } from "axios";
import { apiErrorMessage } from "./apiErrorMessage";
import { notifySystemFeedback } from "./systemFeedback";

export async function downloadFile(url: string, filename: string) {
  try {
    const response = await api.get(url, { responseType: "blob" });
    const href = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(href);
  } catch (error) {
    // Axios request failures are already reported by the shared API interceptor.
    // Keep a local popup only for browser-side download failures.
    if (isAxiosError(error)) return;
    notifySystemFeedback({
      tone: "danger",
      title: "Download could not be completed",
      description: apiErrorMessage(error, "The file could not be downloaded. Check your connection and try again."),
    });
  }
}
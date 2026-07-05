import type { BleDevice, BleStatus, LiveSnapshot, NotificationSettings, SessionRecord } from "./types";

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function getLatestSession() {
  return fetchJson<{ session: SessionRecord | null; live_snapshot?: LiveSnapshot }>("/api/v1/sessions/latest");
}

export function getSessions() {
  return fetchJson<{ items: SessionRecord[] }>("/api/v1/sessions");
}

export function finishSession(sessionId: string) {
  return fetchJson<{ session: SessionRecord; live_snapshot: LiveSnapshot; notification: { sent: boolean; reason?: string } }>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/finish`,
    { method: "POST" }
  );
}

export function getLiveSnapshot(sessionId: string) {
  return fetchJson<LiveSnapshot>(`/api/v1/live/${encodeURIComponent(sessionId)}`);
}

export function scanHeartRateDevices(timeout = 10) {
  return fetchJson<{ timeout: number; items: BleDevice[] }>(`/api/v1/hr/ble/scan?timeout=${timeout}`, {
    method: "POST"
  });
}

export function connectHeartRateDevice(payload: { address?: string; name?: string; session_id?: string }) {
  return fetchJson<BleStatus>("/api/v1/hr/ble/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function disconnectHeartRateDevice() {
  return fetchJson<BleStatus>("/api/v1/hr/ble/disconnect", { method: "POST" });
}

export function getHeartRateStatus() {
  return fetchJson<BleStatus>("/api/v1/hr/ble/status");
}

export function getNotificationSettings() {
  return fetchJson<NotificationSettings>("/api/v1/settings/notifications");
}

export function updateNotificationSettings(payload: Partial<NotificationSettings>) {
  return fetchJson<NotificationSettings>("/api/v1/settings/notifications", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

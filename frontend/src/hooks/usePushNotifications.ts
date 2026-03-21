"use client";

import { useMemo, useState } from "react";
import { subscribeToReport } from "@/lib/api";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const normalized = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(normalized);
  const output = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i += 1) {
    output[i] = rawData.charCodeAt(i);
  }

  return output;
}

export function usePushNotifications(sessionId: string | null) {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const isSupported = useMemo(
    () =>
      typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window,
    []
  );

  async function requestPermission(): Promise<NotificationPermission> {
    if (!isSupported) return "denied";
    return Notification.requestPermission();
  }

  async function subscribe(): Promise<boolean> {
    if (!isSupported || !sessionId) return false;

    const vapidKey = process.env.NEXT_PUBLIC_VAPID_KEY;
    if (!vapidKey) {
      throw new Error("NEXT_PUBLIC_VAPID_KEY is not configured");
    }

    const permission = await requestPermission();
    if (permission !== "granted") {
      return false;
    }

    const registration = await navigator.serviceWorker.register("/sw.js");
    const existing = await registration.pushManager.getSubscription();
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey) as BufferSource,
      }));

    const payload = subscription.toJSON();
    if (!payload.endpoint || !payload.keys?.p256dh || !payload.keys?.auth) {
      throw new Error("Incomplete push subscription payload");
    }

    await subscribeToReport(sessionId, {
      endpoint: payload.endpoint,
      keys: {
        p256dh: payload.keys.p256dh,
        auth: payload.keys.auth,
      },
    });

    setIsSubscribed(true);
    return true;
  }

  return { isSupported, isSubscribed, subscribe, requestPermission };
}

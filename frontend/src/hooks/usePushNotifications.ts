"use client";

import { useMemo, useState } from "react";

export function usePushNotifications(_sessionId: string | null) {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const isSupported = useMemo(() => false, []);

  async function requestPermission(): Promise<NotificationPermission> {
    return "denied";
  }

  async function subscribe(): Promise<boolean> {
    setIsSubscribed(false);
    return false;
  }

  return { isSupported, isSubscribed, subscribe, requestPermission };
}

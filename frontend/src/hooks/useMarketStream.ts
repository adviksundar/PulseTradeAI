import { useEffect, useMemo, useState } from "react";

import { fetchSnapshot, streamUrl } from "../api";
import type { AIInsight, Alert, MarketTick, StreamMessage } from "../types";

const limit = <T,>(items: T[], count: number) => items.slice(0, count);

export function useMarketStream() {
  const [ticks, setTicks] = useState<MarketTick[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [status, setStatus] = useState<"connecting" | "live" | "offline">("connecting");
  const [initialLoaded, setInitialLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;
    fetchSnapshot()
      .then((snapshot) => {
        if (!mounted) return;
        setTicks(snapshot.ticks);
        setInsights(snapshot.insights);
        setAlerts(snapshot.alerts);
        setInitialLoaded(true);
      })
      .catch(() => {
        setInitialLoaded(true);
        setStatus("offline");
      });

    const socket = new WebSocket(streamUrl());
    socket.onopen = () => setStatus("live");
    socket.onclose = () => setStatus("offline");
    socket.onerror = () => setStatus("offline");
    socket.onmessage = (message) => {
      const payload = JSON.parse(message.data) as StreamMessage;
      if (payload.event === "market_tick") {
        setTicks((current) => limit([payload.data as MarketTick, ...current], 80));
      }
      if (payload.event === "ai_insight") {
        setInsights((current) => limit([payload.data as AIInsight, ...current], 40));
      }
      if (payload.event === "alert") {
        setAlerts((current) => limit([payload.data as Alert, ...current], 40));
      }
    };

    return () => {
      mounted = false;
      socket.close();
    };
  }, []);

  const latestByTicker = useMemo(() => {
    const map = new Map<string, MarketTick>();
    for (const tick of ticks) {
      if (!map.has(tick.ticker)) map.set(tick.ticker, tick);
    }
    return [...map.values()].sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [ticks]);

  return { ticks, latestByTicker, insights, alerts, status, initialLoaded };
}

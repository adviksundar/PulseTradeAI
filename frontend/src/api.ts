import type { AgentStatus, DashboardSnapshot, MarketHistory, Watchlist } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchSnapshot(): Promise<DashboardSnapshot> {
  const response = await fetch(`${API_BASE}/api/snapshot`);
  if (!response.ok) {
    throw new Error(`Snapshot request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchWatchlist(): Promise<Watchlist> {
  const response = await fetch(`${API_BASE}/api/watchlist`);
  if (!response.ok) {
    throw new Error(`Watchlist request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchAgentStatus(): Promise<AgentStatus> {
  const response = await fetch(`${API_BASE}/api/agent-status`);
  if (!response.ok) {
    throw new Error(`Agent status request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchMarketHistory(ticker: string, range: string): Promise<MarketHistory> {
  const response = await fetch(`${API_BASE}/api/market/history/${encodeURIComponent(ticker)}?range=${encodeURIComponent(range)}`);
  if (!response.ok) {
    throw new Error(`Market history request failed: ${response.status}`);
  }
  return response.json();
}

export async function addWatchlistTickers(tickers: string[]): Promise<Watchlist> {
  const response = await fetch(`${API_BASE}/api/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tickers })
  });
  if (!response.ok) {
    throw new Error(`Watchlist update failed: ${response.status}`);
  }
  return response.json();
}

export async function removeWatchlistTicker(ticker: string): Promise<Watchlist> {
  const response = await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Watchlist remove failed: ${response.status}`);
  }
  return response.json();
}

export function streamUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) return explicit;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/stream`;
}

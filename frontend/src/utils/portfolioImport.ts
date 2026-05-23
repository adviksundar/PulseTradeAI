import * as XLSX from "xlsx";

const tickerHeaders = new Set(["ticker", "tickers", "symbol", "symbols", "asset", "assets"]);

export async function extractTickersFromPortfolio(file: File): Promise<string[]> {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });
  const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(firstSheet, { defval: "" });

  if (rows.length === 0) return [];

  const headers = Object.keys(rows[0]);
  const tickerHeader = headers.find((header) => tickerHeaders.has(header.trim().toLowerCase())) ?? headers[0];
  const tickers = rows
    .map((row) => normalizeTicker(row[tickerHeader]))
    .filter((ticker): ticker is string => Boolean(ticker));

  return [...new Set(tickers)];
}

export function normalizeTicker(value: unknown): string | null {
  const ticker = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
  if (!ticker || ticker.length > 16) return null;
  if (!/^[A-Z0-9.-]+$/.test(ticker)) return null;
  return ticker;
}

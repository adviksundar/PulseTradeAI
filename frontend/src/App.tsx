import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  Clock3,
  FileSpreadsheet,
  Filter,
  Plus,
  Radio,
  Search,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import {
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  addWatchlistTickers,
  fetchAgentStatus,
  fetchMarketHistory,
  fetchWatchlist,
  removeWatchlistTicker,
} from "./api";
import { useMarketStream } from "./hooks/useMarketStream";
import type {
  AgentStatus,
  AgentTrace,
  AIInsight,
  Alert,
  MarketHistoryPoint,
  MarketTick,
} from "./types";
import {
  extractTickersFromPortfolio,
  normalizeTicker,
} from "./utils/portfolioImport";

type AlertFilter = "All" | "Low" | "Medium" | "High";
type ChartRange = "Live" | "1D" | "5D" | "1M" | "3M" | "1Y" | "5Y" | "Max";
type MarketSort = "ticker" | "change" | "volume" | "updated";
type PriceChartStyle = "Area" | "Line";
type PriceScale = "Padded" | "Tight";
type VolumeMetric = "Log volume" | "Volume" | "Day move";
type VolumeScope = "All" | "Top 3" | "Top 5";
type VolumeSort = "Value" | "Ticker" | "Day move";

function changePct(tick: MarketTick) {
  if (tick.previous_price === 0) return 0;
  const pct = ((tick.price - tick.previous_price) / tick.previous_price) * 100;
  return Math.abs(pct) < 0.005 ? 0 : pct;
}

function formatCurrency(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatPercent(value: number) {
  const normalized = Math.abs(value) < 0.005 ? 0 : value;
  if (normalized === 0) return "0.00%";
  const sign = value >= 0 ? "+" : "";
  const formatted =
    Math.abs(normalized) >= 1000
      ? new Intl.NumberFormat(undefined, {
          notation: "compact",
          maximumFractionDigits: 1,
        }).format(normalized)
      : normalized.toFixed(2);
  return `${sign}${formatted}%`;
}

function paddedDomain(values: number[]) {
  if (values.length === 0) return ["dataMin", "dataMax"] as [string, string];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0);
  const span = Math.max(range * 0.08, Math.abs(max) * 0.002, 0.5);
  const lower = min >= 0 ? Math.max(0, min - span) : min - span;
  return [lower, max + span] as [number, number];
}

function sentimentTone(sentiment: string) {
  if (sentiment === "Bullish")
    return "text-gain bg-emerald-50 border-emerald-200";
  if (sentiment === "Bearish") return "text-loss bg-red-50 border-red-200";
  return "text-slate-700 bg-slate-50 border-slate-200";
}

function formatTime(value?: string) {
  if (!value) return "No updates yet";
  return new Date(value).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatChartTick(value: string, range: ChartRange) {
  const date = new Date(value);
  if (range === "Live")
    return date.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
  if (range === "1D")
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (range === "5D" || range === "1M")
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  return date.toLocaleDateString([], { month: "short", year: "2-digit" });
}

function timeAgo(value?: string) {
  if (!value) return "Awaiting first update";
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export function App() {
  const { ticks, latestByTicker, insights, alerts, status, initialLoaded } =
    useMarketStream();
  const [view, setView] = useState<"dashboard" | "debug">("dashboard");
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [agentStatusError, setAgentStatusError] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [watchlistLoaded, setWatchlistLoaded] = useState(false);
  const [tickerInput, setTickerInput] = useState("");
  const [portfolioMessage, setPortfolioMessage] = useState(
    "Ready for manual tickers or portfolio import.",
  );
  const [activeTicker, setActiveTicker] = useState("AAPL");
  const [alertFilter, setAlertFilter] = useState<AlertFilter>("All");
  const [chartRange, setChartRange] = useState<ChartRange>("1D");
  const [historyPoints, setHistoryPoints] = useState<MarketHistoryPoint[]>([]);
  const [historySource, setHistorySource] = useState("live");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [marketSort, setMarketSort] = useState<MarketSort>("change");
  const [priceChartStyle, setPriceChartStyle] =
    useState<PriceChartStyle>("Area");
  const [priceScale, setPriceScale] = useState<PriceScale>("Padded");
  const [volumeMetric, setVolumeMetric] = useState<VolumeMetric>("Volume");
  const [volumeScope, setVolumeScope] = useState<VolumeScope>("All");
  const [volumeSort, setVolumeSort] = useState<VolumeSort>("Value");
  const visibleTickers = watchlistLoaded
    ? latestByTicker.filter((tick) => watchlist.includes(tick.ticker))
    : latestByTicker;
  const visibleTickerSet = new Set(visibleTickers.map((tick) => tick.ticker));
  const visibleInsights = watchlistLoaded
    ? insights.filter((insight) => watchlist.includes(insight.ticker))
    : insights;
  // Aggregation: choose a canonical insight per ticker for the heatmap.
  // Prefer the most recent insight with confidence >= 0.6; otherwise pick the most recent.
  const getCanonicalInsight = (ticker: string) => {
    const items = insights.filter((i) => i.ticker === ticker);
    if (items.length === 0) return undefined;
    const strong = items.find((i) => i.confidence >= 0.6);
    return strong ?? items[0];
  };
  const visibleAlerts = watchlistLoaded
    ? alerts.filter((alert) => watchlist.includes(alert.ticker))
    : alerts;
  const filteredAlerts =
    alertFilter === "All"
      ? visibleAlerts
      : visibleAlerts.filter((alert) => alert.severity === alertFilter);
  const bullishCount = visibleInsights.filter(
    (insight) => insight.sentiment === "Bullish",
  ).length;
  const bearishCount = visibleInsights.filter(
    (insight) => insight.sentiment === "Bearish",
  ).length;
  const latestAlert = visibleAlerts[0];
  const latestTick = visibleTickers[0];
  const latestUpdate = [
    latestTick?.timestamp,
    visibleInsights[0]?.created_at,
    latestAlert?.created_at,
  ]
    .filter(Boolean)
    .sort(
      (a, b) =>
        new Date(b as string).getTime() - new Date(a as string).getTime(),
    )[0] as string | undefined;
  const hasWatchlist = watchlist.length > 0;
  const hasVisibleTickers = visibleTickers.length > 0;
  const selectedTicker = visibleTickers.some(
    (tick) => tick.ticker === activeTicker,
  )
    ? activeTicker
    : (visibleTickers[0]?.ticker ?? activeTicker);
  const liveChartPoints = ticks
    .filter((tick) => tick.ticker === selectedTicker)
    .slice(0, 120)
    .reverse()
    .map((tick) => ({
      price: tick.price,
      timestamp: tick.timestamp,
      volume: tick.volume,
    }));
  const selectedHistoryPoints =
    chartRange === "Live" || historyPoints.length === 0
      ? liveChartPoints
      : historyPoints.map((point) => ({
          price: point.price,
          timestamp: point.timestamp,
          volume: point.volume,
        }));
  const chartData = selectedHistoryPoints.map((point) => ({
    time: formatChartTick(point.timestamp, chartRange),
    price: point.price,
    volume: point.volume,
  }));
  const selectedTick = visibleTickers.find(
    (tick) => tick.ticker === selectedTicker,
  );
  const selectedTickerChange = selectedTick ? changePct(selectedTick) : 0;
  const chartFirstPrice =
    chartData[0]?.price ?? selectedTick?.previous_price ?? 0;
  const chartLastPrice =
    chartData[chartData.length - 1]?.price ?? selectedTick?.price ?? 0;
  const chartWindowChange = chartFirstPrice
    ? ((chartLastPrice - chartFirstPrice) / chartFirstPrice) * 100
    : 0;
  const priceDomain =
    priceScale === "Padded"
      ? paddedDomain(chartData.map((point) => point.price))
      : (["dataMin", "dataMax"] as [string, string]);
  const volumeData = visibleTickers.map((tick) => ({
    ticker: tick.ticker,
    volume: tick.volume,
    logVolume: Math.log10(Math.max(1, tick.volume)),
    change: changePct(tick),
  }));
  const volumeValueKey =
    volumeMetric === "Log volume"
      ? "logVolume"
      : volumeMetric === "Day move"
        ? "change"
        : "volume";
  const volumeFormatter =
    volumeMetric === "Log volume"
      ? (value: number) => formatCompactNumber(Math.pow(10, value))
      : volumeMetric === "Day move"
        ? formatPercent
        : formatCompactNumber;
  const moveValues = volumeData.map((item) => item.change);
  const maxAbsMove = Math.max(1, ...moveValues.map((value) => Math.abs(value)));
  const volumeDomain =
    volumeMetric === "Day move"
      ? ([-maxAbsMove * 1.2, maxAbsMove * 1.2] as [number, number])
      : ([0, "dataMax"] as [number | string, number | string]);
  const sortedVolumeData = [...volumeData].sort((a, b) => {
    if (volumeSort === "Ticker") return a.ticker.localeCompare(b.ticker);
    if (volumeSort === "Day move")
      return Math.abs(b.change) - Math.abs(a.change);
    return Math.abs(b[volumeValueKey]) - Math.abs(a[volumeValueKey]);
  });
  const scopedVolumeData =
    volumeScope === "Top 3"
      ? sortedVolumeData.slice(0, 3)
      : volumeScope === "Top 5"
        ? sortedVolumeData.slice(0, 5)
        : sortedVolumeData;
  const denseVolumeLabels = scopedVolumeData.length > 6;
  const volumeChartWidth = denseVolumeLabels
    ? Math.max(760, scopedVolumeData.length * 116)
    : "100%";
  const sortedMarketRows = [...visibleTickers].sort((a, b) => {
    if (marketSort === "ticker") return a.ticker.localeCompare(b.ticker);
    if (marketSort === "volume") return b.volume - a.volume;
    if (marketSort === "updated")
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    return Math.abs(changePct(b)) - Math.abs(changePct(a));
  });
  const selectedEvent =
    agentStatus?.recent_events.find(
      (event) => event.event_id === selectedEventId,
    ) ??
    agentStatus?.recent_events[0] ??
    null;

  useEffect(() => {
    fetchWatchlist()
      .then((data) => {
        setWatchlist(data.tickers);
        setWatchlistLoaded(true);
        if (data.tickers[0]) setActiveTicker(data.tickers[0]);
      })
      .catch(() => {
        setWatchlistLoaded(true);
        setPortfolioMessage("Watchlist API is offline.");
      });
  }, []);

  useEffect(() => {
    if (view !== "debug") return;
    let mounted = true;
    async function loadAgentStatus() {
      try {
        const data = await fetchAgentStatus();
        if (!mounted) return;
        setAgentStatus(data);
        setAgentStatusError(null);
        setSelectedEventId(
          (current) => current ?? data.recent_events[0]?.event_id ?? null,
        );
      } catch {
        if (!mounted) return;
        setAgentStatusError("Unable to load agent status.");
      }
    }
    loadAgentStatus();
    const interval = window.setInterval(loadAgentStatus, 5000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [view]);

  useEffect(() => {
    if (!selectedTicker || chartRange === "Live") {
      setHistoryPoints([]);
      setHistorySource("live");
      setHistoryError(null);
      return;
    }
    let mounted = true;
    setHistoryLoading(true);
    setHistoryError(null);
    fetchMarketHistory(selectedTicker, chartRange)
      .then((history) => {
        if (!mounted) return;
        setHistoryPoints(history.points);
        setHistorySource(history.source);
      })
      .catch(() => {
        if (!mounted) return;
        setHistoryPoints([]);
        setHistorySource("live");
        setHistoryError(
          "Historical range unavailable. Showing collected live ticks.",
        );
      })
      .finally(() => {
        if (mounted) setHistoryLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [selectedTicker, chartRange]);

  async function addTickers(tickers: string[], source: "manual" | "portfolio") {
    const normalized = [
      ...new Set(
        tickers
          .map(normalizeTicker)
          .filter((ticker): ticker is string => Boolean(ticker)),
      ),
    ];
    if (normalized.length === 0) {
      setPortfolioMessage("No valid ticker symbols found.");
      return;
    }
    const updated = await addWatchlistTickers(normalized);
    setWatchlist(updated.tickers);
    const accepted = normalized.filter((ticker) =>
      updated.tickers.includes(ticker),
    );
    if (accepted[0]) setActiveTicker(accepted[0]);
    const acceptedText =
      accepted.length > 0
        ? source === "portfolio"
          ? `Imported ${accepted.length} ticker${accepted.length === 1 ? "" : "s"} from portfolio.`
          : `Added ${accepted.join(", ")} to monitoring.`
        : "No new tickers were added.";
    const rejectedText =
      updated.rejected.length > 0
        ? ` Rejected invalid ticker${updated.rejected.length === 1 ? "" : "s"}: ${updated.rejected.join(", ")}.`
        : "";
    setPortfolioMessage(`${acceptedText}${rejectedText}`);
  }

  async function handleTickerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await addTickers(
        tickerInput
          .split(/[,\n]/)
          .map((ticker) => ticker.trim())
          .filter(Boolean),
        "manual",
      );
      setTickerInput("");
    } catch {
      setPortfolioMessage("Unable to update watchlist.");
    }
  }

  async function handlePortfolioUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const tickers = await extractTickersFromPortfolio(file);
      await addTickers(tickers, "portfolio");
    } catch {
      setPortfolioMessage("Could not read that portfolio file.");
    } finally {
      event.target.value = "";
    }
  }

  async function handleRemoveTicker(ticker: string) {
    try {
      const updated = await removeWatchlistTicker(ticker);
      setWatchlist(updated.tickers);
      if (ticker === activeTicker) {
        setActiveTicker(
          updated.tickers[0] ??
            latestByTicker.find((tick) => tick.ticker !== ticker)?.ticker ??
            "AAPL",
        );
      }
      setPortfolioMessage(`Removed ${ticker} from monitoring.`);
    } catch {
      setPortfolioMessage(`Unable to remove ${ticker}.`);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 text-ink">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-signal">
              PulseTradeAI
            </p>
            <h1 className="text-2xl font-semibold md:text-3xl">
              Real-time market intelligence
            </h1>
          </div>
          <button
            className="flex items-center gap-2 rounded border border-line bg-panel px-3 py-2 text-sm font-medium shadow-sm transition hover:border-signal hover:bg-blue-50"
            onClick={() => setView(view === "debug" ? "dashboard" : "debug")}
            type="button"
          >
            {view === "debug" ? (
              <ArrowLeft className="h-4 w-4 text-signal" />
            ) : (
              <Radio
                className={
                  status === "live" ? "h-4 w-4 text-gain" : "h-4 w-4 text-loss"
                }
              />
            )}
            <span>
              {view === "debug"
                ? "Dashboard"
                : status === "live"
                  ? "Live"
                  : "Offline"}
            </span>
          </button>
        </div>
      </header>

      {view === "debug" ? (
        <AgentDebugPage
          agentStatus={agentStatus}
          error={agentStatusError}
          selectedEventId={selectedEvent?.event_id ?? null}
          onSelectEvent={setSelectedEventId}
        />
      ) : (
        <section className="mx-auto max-w-7xl space-y-5 px-5 py-5">
          <Panel
            title="Portfolio monitor"
            icon={<FileSpreadsheet className="h-4 w-4 text-signal" />}
          >
            <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <form
                className="flex flex-col gap-3 sm:flex-row"
                onSubmit={handleTickerSubmit}
              >
                <input
                  className="min-h-10 flex-1 rounded border border-line px-3 text-sm outline-none focus:border-signal focus:ring-2 focus:ring-blue-100"
                  onChange={(event) => setTickerInput(event.target.value)}
                  placeholder="Add tickers, e.g. AMD, META, ETH-USD"
                  value={tickerInput}
                />
                <button
                  className="inline-flex min-h-10 items-center justify-center gap-2 rounded bg-signal px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
                  type="submit"
                >
                  <Plus className="h-4 w-4" />
                  Add
                </button>
              </form>

              <label className="flex min-h-10 cursor-pointer items-center justify-center gap-2 rounded border border-dashed border-slate-300 bg-panel px-4 text-sm font-semibold text-slate-700 transition hover:border-signal hover:bg-blue-50">
                <FileSpreadsheet className="h-4 w-4" />
                Upload Excel or CSV portfolio
                <input
                  accept=".xlsx,.xls,.csv"
                  className="sr-only"
                  onChange={handlePortfolioUpload}
                  type="file"
                />
              </label>
            </div>

            <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <p className="text-sm text-slate-500">{portfolioMessage}</p>
              <div className="flex max-h-24 flex-wrap gap-2 overflow-y-auto lg:justify-end">
                {watchlist.map((ticker) => (
                  <button
                    aria-label={`Remove ${ticker}`}
                    className="inline-flex items-center gap-1 rounded border border-line bg-white px-2 py-1 text-xs font-semibold text-slate-700 transition hover:border-red-200 hover:bg-red-50 hover:text-loss"
                    key={ticker}
                    onClick={() => handleRemoveTicker(ticker)}
                    type="button"
                  >
                    {ticker}
                    <X className="h-3 w-3" />
                  </button>
                ))}
              </div>
            </div>
          </Panel>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Tracked assets"
              value={watchlist.length.toString()}
              icon={<BarChart3 className="h-4 w-4" />}
            />
            <MetricCard
              label="Bullish signals"
              value={bullishCount.toString()}
              tone="gain"
              icon={<TrendingUp className="h-4 w-4" />}
            />
            <MetricCard
              label="Bearish signals"
              value={bearishCount.toString()}
              tone="loss"
              icon={<TrendingDown className="h-4 w-4" />}
            />
            <MetricCard
              detail={timeAgo(latestUpdate)}
              label="Last updated"
              value={formatTime(latestUpdate)}
              tone={status === "live" ? "gain" : "warn"}
              icon={<Clock3 className="h-4 w-4" />}
            />
          </div>

          {!initialLoaded || !watchlistLoaded ? <LoadingState /> : null}

          {hasWatchlist ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {visibleTickers.map((tick) => (
                <TickerCard
                  active={tick.ticker === selectedTicker}
                  key={tick.ticker}
                  onSelect={() => setActiveTicker(tick.ticker)}
                  tick={tick}
                />
              ))}
            </div>
          ) : (
            <EmptyWatchlist />
          )}

          {hasVisibleTickers ? (
            <div className="grid min-w-0 items-stretch gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
              <Panel
                title={`${selectedTicker} price movement`}
                icon={<Activity className="h-4 w-4 text-signal" />}
              >
                <div className="mb-4 flex flex-col gap-3">
                  <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
                    <ChartStat
                      label="Price"
                      value={
                        selectedTick ? formatCurrency(selectedTick.price) : "--"
                      }
                    />
                    <ChartStat
                      label={`${chartRange} move`}
                      tone={chartWindowChange >= 0 ? "gain" : "loss"}
                      value={formatPercent(chartWindowChange)}
                    />
                    <ChartStat
                      label="Day move"
                      tone={selectedTickerChange >= 0 ? "gain" : "loss"}
                      value={formatPercent(selectedTickerChange)}
                    />
                  </div>
                  <div className="grid w-full grid-cols-4 gap-2 md:grid-cols-8">
                    {(
                      [
                        "Live",
                        "1D",
                        "5D",
                        "1M",
                        "3M",
                        "1Y",
                        "5Y",
                        "Max",
                      ] as ChartRange[]
                    ).map((range) => (
                      <button
                        className={`rounded border px-3 py-1 text-xs font-semibold transition ${
                          chartRange === range
                            ? "border-signal bg-blue-50 text-signal"
                            : "border-line bg-white text-slate-600 hover:border-slate-300"
                        }`}
                        key={range}
                        onClick={() => setChartRange(range)}
                        type="button"
                      >
                        {range}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>
                    Source:{" "}
                    {chartRange === "Live"
                      ? "collected live ticks"
                      : historySource}
                  </span>
                  <span>-</span>
                  <span>{chartData.length} points</span>
                  {historyLoading ? <span>- Loading range...</span> : null}
                  {historyError ? (
                    <span className="text-amber-700">- {historyError}</span>
                  ) : null}
                </div>
                <div className="mb-4 grid gap-3 md:grid-cols-2">
                  <ControlGroup
                    label="Chart style"
                    onSelect={(value) =>
                      setPriceChartStyle(value as PriceChartStyle)
                    }
                    options={["Area", "Line"]}
                    value={priceChartStyle}
                  />
                  <ControlGroup
                    label="Y-axis"
                    onSelect={(value) => setPriceScale(value as PriceScale)}
                    options={["Padded", "Tight"]}
                    value={priceScale}
                  />
                </div>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={chartData}
                      margin={{ left: 8, right: 16, top: 8, bottom: 22 }}
                    >
                      <defs>
                        <linearGradient
                          id="priceFill"
                          x1="0"
                          x2="0"
                          y1="0"
                          y2="1"
                        >
                          <stop
                            offset="5%"
                            stopColor="#2454d6"
                            stopOpacity={0.24}
                          />
                          <stop
                            offset="95%"
                            stopColor="#2454d6"
                            stopOpacity={0.02}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#edf0f5" vertical={false} />
                      <XAxis
                        dataKey="time"
                        tickLine={false}
                        axisLine={false}
                        minTickGap={42}
                        dy={12}
                      />
                      <YAxis
                        domain={priceDomain}
                        tickFormatter={(value) => Number(value).toFixed(2)}
                        width={86}
                        tickLine={false}
                        axisLine={false}
                        dx={-6}
                      />
                      <Tooltip
                        formatter={(value) => formatCurrency(Number(value))}
                      />
                      <Area
                        dataKey="price"
                        dot={priceChartStyle === "Line"}
                        fill={
                          priceChartStyle === "Area"
                            ? "url(#priceFill)"
                            : "transparent"
                        }
                        stroke="#2454d6"
                        strokeWidth={2}
                        type="monotone"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </Panel>

              <Panel
                title="Volume pulse"
                icon={<BarChart3 className="h-4 w-4 text-signal" />}
              >
                <div className="mb-4 grid gap-3">
                  <ControlGroup
                    label="Metric"
                    onSelect={(value) => setVolumeMetric(value as VolumeMetric)}
                    options={["Volume", "Log volume", "Day move"]}
                    value={volumeMetric}
                  />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <ControlGroup
                      label="Scope"
                      onSelect={(value) => setVolumeScope(value as VolumeScope)}
                      options={["All", "Top 3", "Top 5"]}
                      value={volumeScope}
                    />
                    <ControlGroup
                      label="Sort"
                      onSelect={(value) => setVolumeSort(value as VolumeSort)}
                      options={["Value", "Ticker", "Day move"]}
                      value={volumeSort}
                    />
                  </div>
                  <p className="text-xs text-slate-500">
                    Day move compares the latest price with the previous close
                    when yfinance data is available. Volume is the latest
                    reported trading volume.
                  </p>
                </div>
                {scopedVolumeData.length > 0 ? (
                  <div className="min-w-0 overflow-x-auto overflow-y-hidden pb-1">
                    <div
                      className="h-96 max-w-full"
                      style={{ width: volumeChartWidth }}
                    >
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          barCategoryGap="24%"
                          data={scopedVolumeData}
                          margin={{
                            left: 4,
                            right: 28,
                            top: 22,
                            bottom: denseVolumeLabels ? 54 : 16,
                          }}
                        >
                          <CartesianGrid stroke="#edf0f5" vertical={false} />
                          <XAxis
                            angle={denseVolumeLabels ? -35 : 0}
                            dataKey="ticker"
                            height={denseVolumeLabels ? 68 : 38}
                            interval={0}
                            textAnchor={denseVolumeLabels ? "end" : "middle"}
                            tickLine={false}
                            axisLine={false}
                          />
                          <YAxis
                            domain={volumeDomain}
                            tickFormatter={(value) =>
                              volumeFormatter(Number(value))
                            }
                            tickLine={false}
                            axisLine={false}
                            width={76}
                          />
                          <Tooltip
                            formatter={(value) =>
                              volumeFormatter(Number(value))
                            }
                          />
                          {volumeMetric === "Day move" ? (
                            <ReferenceLine y={0} stroke="#94a3b8" />
                          ) : null}
                          <Bar
                            dataKey={volumeValueKey}
                            maxBarSize={72}
                            radius={[4, 4, 0, 0]}
                          >
                            {scopedVolumeData.map((item) => (
                              <Cell
                                fill={item.change >= 0 ? "#16a34a" : "#dc2626"}
                                key={item.ticker}
                              />
                            ))}
                            {volumeMetric === "Day move" ? (
                              <LabelList
                                dataKey="change"
                                formatter={(value: number) =>
                                  formatPercent(value)
                                }
                                position="top"
                              />
                            ) : null}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                ) : (
                  <EmptyPanel message="Add tickers to compare volume and day movement." />
                )}
              </Panel>
            </div>
          ) : hasWatchlist ? (
            <PendingMarketData />
          ) : null}

          {hasVisibleTickers ? (
            <Panel
              title="Market table"
              icon={<BarChart3 className="h-4 w-4 text-signal" />}
            >
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Filter className="h-4 w-4 text-slate-500" />
                <span className="text-xs font-semibold uppercase text-slate-500">
                  Sort by
                </span>
                {(
                  [
                    ["change", "Day move"],
                    ["volume", "Volume"],
                    ["updated", "Updated"],
                    ["ticker", "Ticker"],
                  ] as [MarketSort, string][]
                ).map(([sort, label]) => (
                  <button
                    className={`rounded border px-3 py-1 text-xs font-semibold transition ${
                      marketSort === sort
                        ? "border-signal bg-blue-50 text-signal"
                        : "border-line bg-white text-slate-600 hover:border-slate-300"
                    }`}
                    key={sort}
                    onClick={() => setMarketSort(sort)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="mb-3 text-xs text-slate-500">
                Sorting reorders the visible tickers. Day move sorts by absolute
                move versus previous close; Updated sorts by newest quote
                refresh.
              </p>
              <MarketTable
                rows={sortedMarketRows}
                selectedTicker={selectedTicker}
                onSelectTicker={setActiveTicker}
              />
            </Panel>
          ) : null}

          {hasWatchlist ? (
            <Panel
              title="Sentiment heatmap"
              icon={<ShieldAlert className="h-4 w-4 text-signal" />}
            >
              {visibleTickerSet.size > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {watchlist.map((ticker) => (
                    <SentimentTile
                      key={ticker}
                      ticker={ticker}
                      insight={getCanonicalInsight(ticker)}
                    />
                  ))}
                </div>
              ) : (
                <EmptyPanel message="Sentiment tiles will appear after the first market and news refresh." />
              )}
            </Panel>
          ) : null}

          <div className="grid items-stretch gap-5 lg:grid-cols-2">
            <Panel
              className="h-[36rem] overflow-hidden"
              title="AI insights"
              icon={<BrainCircuit className="h-4 w-4 text-signal" />}
            >
              {visibleInsights.length > 0 ? (
                <div className="h-full min-h-0 space-y-3 overflow-y-auto pr-1">
                  {visibleInsights.slice(0, 14).map((insight) => (
                    <InsightItem key={insight.event_id} insight={insight} />
                  ))}
                </div>
              ) : (
                <EmptyPanel message="AI insights will appear as monitored tickers receive mock news events." />
              )}
            </Panel>

            <Panel
              className="h-[36rem] overflow-hidden"
              title="Live alerts"
              icon={<AlertTriangle className="h-4 w-4 text-loss" />}
            >
              {hasWatchlist || visibleAlerts.length > 0 ? (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Filter className="h-4 w-4 text-slate-500" />
                  {(["All", "High", "Medium", "Low"] as AlertFilter[]).map(
                    (filter) => (
                      <button
                        className={`rounded border px-3 py-1 text-xs font-semibold transition ${
                          alertFilter === filter
                            ? "border-signal bg-blue-50 text-signal"
                            : "border-line bg-white text-slate-600 hover:border-slate-300"
                        }`}
                        key={filter}
                        onClick={() => setAlertFilter(filter)}
                        type="button"
                      >
                        {filter}
                      </button>
                    ),
                  )}
                </div>
              ) : null}
              {filteredAlerts.length > 0 ? (
                <div
                  className={`min-h-0 space-y-3 overflow-y-auto pr-1 ${
                    hasWatchlist || visibleAlerts.length > 0
                      ? "h-[calc(100%-2.25rem)]"
                      : "h-full"
                  }`}
                >
                  {filteredAlerts.slice(0, 14).map((alert) => (
                    <AlertItem key={alert.alert_id} alert={alert} />
                  ))}
                </div>
              ) : (
                <EmptyPanel
                  message={
                    hasWatchlist
                      ? "No alerts match the selected severity filter."
                      : "Alerts will appear as monitored tickers trigger market or sentiment events."
                  }
                />
              )}
            </Panel>
          </div>
        </section>
      )}
    </main>
  );
}

function AgentDebugPage({
  agentStatus,
  error,
  selectedEventId,
  onSelectEvent,
}: {
  agentStatus: AgentStatus | null;
  error: string | null;
  selectedEventId: string | null;
  onSelectEvent: (eventId: string) => void;
}) {
  const selectedEvent =
    agentStatus?.recent_events.find(
      (event) => event.event_id === selectedEventId,
    ) ??
    agentStatus?.recent_events[0] ??
    null;
  const traceByAgent = new Map(
    (selectedEvent?.trace ?? agentStatus?.latest_trace ?? []).map((trace) => [
      trace.agent,
      trace,
    ]),
  );

  return (
    <section className="mx-auto max-w-7xl space-y-5 px-5 py-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="OpenAI mode"
          value={agentStatus?.openai_enabled ? "Enabled" : "Disabled"}
          detail={agentStatus?.use_mock_ai ? "Mock AI on" : "Mock AI off"}
          tone={agentStatus?.openai_enabled ? "gain" : "warn"}
          icon={<BrainCircuit className="h-4 w-4" />}
        />
        <MetricCard
          label="Processed events"
          value={(agentStatus?.processed_events ?? 0).toString()}
          detail="Since backend start"
          icon={<Activity className="h-4 w-4" />}
        />
        <MetricCard
          label="OpenAI calls"
          value={(
            agentStatus?.total_openai_successes ??
            agentStatus?.total_openai_calls ??
            0
          ).toString()}
          detail={`${agentStatus?.total_openai_attempts ?? 0} attempts since startup`}
          tone="signal"
          icon={<BarChart3 className="h-4 w-4" />}
        />
        <MetricCard
          label="Latest ticker"
          value={agentStatus?.latest_ticker ?? "--"}
          detail={
            agentStatus?.latest_completed_at
              ? `Completed ${timeAgo(agentStatus.latest_completed_at)}`
              : "Waiting for event"
          }
          tone="warn"
          icon={<Clock3 className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="News loops"
          value={(agentStatus?.news_loop_count ?? 0).toString()}
          detail={`Every ${agentStatus?.news_poll_seconds ?? 0}s`}
          icon={<Clock3 className="h-4 w-4" />}
        />
        <MetricCard
          label="News events seen"
          value={(agentStatus?.news_events_seen ?? 0).toString()}
          detail={
            agentStatus?.last_news_event_at
              ? `Last event ${timeAgo(agentStatus.last_news_event_at)}`
              : "No news event yet"
          }
          tone="signal"
          icon={<FileSpreadsheet className="h-4 w-4" />}
        />
        <MetricCard
          label="Last news loop"
          value={
            agentStatus?.last_news_loop_completed_at
              ? timeAgo(agentStatus.last_news_loop_completed_at)
              : "--"
          }
          detail={
            agentStatus?.last_news_loop_started_at
              ? `Started ${timeAgo(agentStatus.last_news_loop_started_at)}`
              : "Waiting"
          }
          tone="warn"
          icon={<Activity className="h-4 w-4" />}
        />
        <MetricCard
          label="Market loops"
          value={(agentStatus?.market_loop_count ?? 0).toString()}
          detail={
            agentStatus?.last_market_loop_at
              ? `Last tick ${timeAgo(agentStatus.last_market_loop_at)}`
              : "No market tick yet"
          }
          tone="gain"
          icon={<BarChart3 className="h-4 w-4" />}
        />
      </div>

      {error ? <EmptyPanel message={error} /> : null}

      <Panel
        title="Agent workflow"
        icon={<BrainCircuit className="h-4 w-4 text-signal" />}
      >
        <div className="mb-4 rounded border border-line bg-panel p-3 text-sm text-slate-600">
          Every news event moves through these stages from left to right. OpenAI
          stages make API calls and use tokens; local policy stages run inside
          the backend and do not call OpenAI.
        </div>
        <div className="grid gap-3 lg:grid-cols-5">
          {(agentStatus?.stage_definitions ?? []).map(
            (stage, index, stages) => (
              <div className="flex items-stretch gap-3" key={stage.agent}>
                <AgentStageCard
                  stage={stage}
                  totalAttempts={
                    agentStatus?.stage_call_counts[stage.agent] ?? 0
                  }
                  totalSuccesses={
                    agentStatus?.stage_success_counts[stage.agent] ?? 0
                  }
                  trace={traceByAgent.get(stage.agent)}
                />
                {index < stages.length - 1 ? (
                  <div className="hidden items-center text-slate-400 lg:flex">
                    <ArrowRight className="h-5 w-5" />
                  </div>
                ) : null}
              </div>
            ),
          )}
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[0.9fr_1.4fr]">
        <Panel
          title="Recent events"
          icon={<Clock3 className="h-4 w-4 text-signal" />}
        >
          <div className="max-h-[24rem] space-y-2 overflow-y-auto pr-1">
            {(agentStatus?.recent_events ?? []).map((event) => (
              <button
                className={`w-full rounded border p-3 text-left transition ${
                  selectedEvent?.event_id === event.event_id
                    ? "border-signal bg-blue-50"
                    : "border-line bg-white hover:border-slate-300"
                }`}
                key={event.event_id}
                onClick={() => onSelectEvent(event.event_id)}
                type="button"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{event.ticker}</span>
                  <span className="text-xs text-slate-500">
                    {timeAgo(event.timestamp)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{event.headline}</p>
              </button>
            ))}
            {agentStatus && agentStatus.recent_events.length === 0 ? (
              <EmptyPanel message="No agent events have completed yet. Wait for the next news poll." />
            ) : null}
          </div>
        </Panel>

        <Panel
          title="Stage logs"
          icon={<Filter className="h-4 w-4 text-signal" />}
        >
          <div className="max-h-[24rem] space-y-2 overflow-y-auto pr-1">
            {(agentStatus?.logs ?? []).map((log, index) => (
              <article
                className="rounded border border-line bg-panel p-3"
                key={`${log.event_id}-${log.agent}-${index}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <StatusPill status={log.status} />
                    <span className="text-sm font-semibold">
                      {labelizeAgent(log.agent)}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {timeAgo(log.created_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-700">
                  {log.ticker}: {log.headline}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  {log.uses_openai
                    ? `OpenAI - ${log.model} - ${log.successful_calls}/${log.calls_made} calls succeeded`
                    : "Local policy - no API call"}
                  {log.message ? ` - ${log.message}` : ""}
                </p>
              </article>
            ))}
            {agentStatus && agentStatus.logs.length === 0 ? (
              <EmptyPanel message="Stage logs will appear after the next workflow run." />
            ) : null}
          </div>
        </Panel>
      </div>
    </section>
  );
}

function AgentStageCard({
  stage,
  totalAttempts,
  totalSuccesses,
  trace,
}: {
  stage: AgentStatus["stage_definitions"][number];
  totalAttempts: number;
  totalSuccesses: number;
  trace?: AgentTrace;
}) {
  return (
    <article className="min-h-44 flex-1 rounded border border-line bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{stage.label}</h3>
          <p className="mt-1 text-xs text-slate-500">{stage.description}</p>
        </div>
        <StatusPill status={trace?.status ?? "fallback"} />
      </div>
      <div className="mt-4 space-y-2 text-xs text-slate-600">
        <p>Execution: {stage.uses_openai ? "OpenAI API" : "Backend code"}</p>
        {stage.uses_openai ? (
          <>
            <p>Model: {stage.model}</p>
            <p>
              Since startup: {totalSuccesses}/{totalAttempts} API calls
              succeeded
            </p>
          </>
        ) : (
          <>
            <p>Since startup: no OpenAI calls</p>
          </>
        )}
        <p>
          Last completed: {trace ? timeAgo(trace.created_at) : "Awaiting event"}
        </p>
        {trace?.message ? (
          <p className="text-slate-500">{trace.message}</p>
        ) : null}
      </div>
    </article>
  );
}

function StatusPill({ status }: { status: "ok" | "fallback" | "error" }) {
  const styles = {
    ok: "border-emerald-200 bg-emerald-50 text-gain",
    fallback: "border-amber-200 bg-amber-50 text-amber-700",
    error: "border-red-200 bg-red-50 text-loss",
  };
  return (
    <span
      className={`rounded border px-2 py-1 text-xs font-semibold ${styles[status]}`}
    >
      {status}
    </span>
  );
}

function labelizeAgent(agent: string) {
  return agent
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function EmptyWatchlist() {
  return (
    <section className="rounded border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded bg-blue-50 text-signal">
        <Search className="h-5 w-5" />
      </div>
      <h2 className="mt-4 text-lg font-semibold">
        No tickers are being monitored
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-slate-500">
        Add a valid symbol such as AAPL, MSFT, SPY, or BTC-USD, or upload a
        portfolio file with a ticker or symbol column.
      </p>
    </section>
  );
}

function PendingMarketData() {
  return (
    <section className="rounded border border-line bg-white p-6 text-center shadow-sm">
      <h2 className="text-base font-semibold">Waiting for market data</h2>
      <p className="mt-2 text-sm text-slate-500">
        Newly added tickers will appear here after the next quote refresh.
      </p>
    </section>
  );
}

function ChartStat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss" | "neutral";
}) {
  const toneClass =
    tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink";
  return (
    <div className="min-w-0 rounded border border-line bg-panel px-3 py-2">
      <p className="text-[11px] font-medium uppercase text-slate-500">
        {label}
      </p>
      <p
        className={`mt-1 break-words text-sm font-semibold leading-tight sm:text-base ${toneClass}`}
      >
        {value}
      </p>
    </div>
  );
}

function ControlGroup({
  label,
  onSelect,
  options,
  value,
}: {
  label: string;
  options: string[];
  value: string;
  onSelect: (value: string) => void;
}) {
  return (
    <div className="rounded border border-line bg-panel p-2">
      <p className="mb-2 text-[11px] font-semibold uppercase text-slate-500">
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            className={`rounded border px-3 py-1 text-xs font-semibold transition ${
              value === option
                ? "border-signal bg-blue-50 text-signal"
                : "border-line bg-white text-slate-600 hover:border-slate-300"
            }`}
            key={option}
            onClick={() => onSelect(option)}
            type="button"
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

function MarketTable({
  rows,
  selectedTicker,
  onSelectTicker,
}: {
  rows: MarketTick[];
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded border border-line">
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-panel text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2 font-semibold">Ticker</th>
              <th className="px-3 py-2 font-semibold">Price</th>
              <th className="px-3 py-2 font-semibold">Day move</th>
              <th className="px-3 py-2 font-semibold">Volume</th>
              <th className="px-3 py-2 font-semibold">Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((tick) => {
              const change = changePct(tick);
              const selected = tick.ticker === selectedTicker;
              return (
                <tr
                  className={`cursor-pointer border-t border-line transition hover:bg-blue-50 ${
                    selected ? "bg-blue-50" : "bg-white"
                  }`}
                  key={tick.event_id}
                  onClick={() => onSelectTicker(tick.ticker)}
                >
                  <td className="px-3 py-3 font-semibold">{tick.ticker}</td>
                  <td className="px-3 py-3">{formatCurrency(tick.price)}</td>
                  <td
                    className={`px-3 py-3 font-semibold ${change >= 0 ? "text-gain" : "text-loss"}`}
                  >
                    {formatPercent(change)}
                  </td>
                  <td className="px-3 py-3">
                    {formatCompactNumber(tick.volume)}
                  </td>
                  <td className="px-3 py-3 text-slate-500">
                    {timeAgo(tick.timestamp)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          className="h-32 animate-pulse rounded border border-line bg-white p-3 shadow-sm"
          key={index}
        >
          <div className="h-4 w-20 rounded bg-slate-200" />
          <div className="mt-5 h-7 w-28 rounded bg-slate-200" />
          <div className="mt-4 h-3 w-16 rounded bg-slate-200" />
        </div>
      ))}
    </section>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="rounded border border-dashed border-slate-300 bg-panel p-5 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}

function MetricCard({
  detail,
  label,
  value,
  icon,
  tone = "signal",
}: {
  label: string;
  value: string;
  detail?: string;
  icon: ReactNode;
  tone?: "signal" | "gain" | "loss" | "warn";
}) {
  const tones = {
    signal: "text-signal bg-blue-50",
    gain: "text-gain bg-emerald-50",
    loss: "text-loss bg-red-50",
    warn: "text-amber-700 bg-amber-50",
  };
  return (
    <article className="rounded border border-line bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <span className={`rounded p-2 ${tones[tone]}`}>{icon}</span>
      </div>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </article>
  );
}

function TickerCard({
  active,
  onSelect,
  tick,
}: {
  active: boolean;
  onSelect: () => void;
  tick: MarketTick;
}) {
  const change = changePct(tick);
  const positive = change >= 0;
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <button
      className={`rounded border bg-white p-3 text-left shadow-sm transition hover:border-slate-300 hover:shadow ${
        active ? "border-signal ring-2 ring-blue-100" : "border-line"
      }`}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{tick.ticker}</h2>
        <Icon
          className={positive ? "h-4 w-4 text-gain" : "h-4 w-4 text-loss"}
        />
      </div>
      <p className="mt-2 text-2xl font-semibold">
        ${tick.price.toLocaleString()}
      </p>
      <p
        className={
          positive
            ? "text-sm font-medium text-gain"
            : "text-sm font-medium text-loss"
        }
      >
        {formatPercent(change)}
      </p>
      <p className="mt-2 text-xs text-slate-500">
        Vol {tick.volume.toLocaleString()}
      </p>
      <p className="mt-1 text-xs text-slate-400">
        Updated {timeAgo(tick.timestamp)}
      </p>
    </button>
  );
}

function Panel({
  title,
  icon,
  children,
  className = "",
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`min-w-0 flex flex-col rounded border border-line bg-white p-4 shadow-sm ${className}`}
    >
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <h2 className="text-base font-semibold">{title}</h2>
        {icon}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

function InsightItem({ insight }: { insight: AIInsight }) {
  return (
    <article className="rounded border border-line bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold">{insight.ticker}</span>
        <span
          className={`rounded border px-2 py-1 text-xs font-semibold ${sentimentTone(insight.sentiment)}`}
        >
          {insight.sentiment}
        </span>
      </div>
      <p className="text-sm text-slate-700">{insight.summary}</p>
      <div className="mt-3 h-1.5 rounded bg-slate-100">
        <div
          className="h-1.5 rounded bg-signal"
          style={{ width: `${insight.confidence * 100}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Confidence {(insight.confidence * 100).toFixed(0)}% -{" "}
        {timeAgo(insight.created_at)}
      </p>
    </article>
  );
}

function SentimentTile({
  ticker,
  insight,
}: {
  ticker: string;
  insight?: AIInsight;
}) {
  // Use `confidence` (0..1) for the displayed heatmap strength so neutral shows a
  // sensible percentage (e.g. 52%) instead of raw signed `sentiment_score` which is
  // centered at 0.0 for neutral.
  const confidence = insight?.confidence ?? 0;
  const label = insight?.sentiment ?? "Neutral";
  const width = `${Math.max(8, Math.round(confidence * 100))}%`;
  const bar =
    label === "Bullish"
      ? "bg-gain"
      : label === "Bearish"
        ? "bg-loss"
        : "bg-slate-400";
  return (
    <article className={`rounded border p-3 ${sentimentTone(label)}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{ticker}</h3>
        <span className="text-xs font-semibold">{label}</span>
      </div>
      <div className="mt-3 h-2 rounded bg-white/70">
        <div className={`h-2 rounded ${bar}`} style={{ width }} />
      </div>
      <p className="mt-2 text-xs opacity-80">
        {insight
          ? `${(confidence * 100).toFixed(0)}% - ${timeAgo(insight.created_at)}`
          : "Awaiting insight"}
      </p>
    </article>
  );
}

function AlertItem({ alert }: { alert: Alert }) {
  return (
    <article className="rounded border border-line bg-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{alert.title}</h3>
        <span className="text-xs font-semibold text-slate-500">
          {alert.severity}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-700">{alert.message}</p>
      <p className="mt-2 text-xs text-slate-500">{timeAgo(alert.created_at)}</p>
    </article>
  );
}

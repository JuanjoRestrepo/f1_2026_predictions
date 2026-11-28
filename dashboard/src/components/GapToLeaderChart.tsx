"use client";

import { useState, useMemo } from "react";
import { Activity, AlertTriangle, Pause } from "lucide-react";

interface SafetyCarWindow {
  start_lap: number;
  end_lap: number;
  type: "SC" | "VSC" | "RED";
}

interface GapDriver {
  driver: string;
  team: string;
  color: string;
  gaps_s: Record<string, number>;
}

interface GapToLeaderData {
  event: string;
  year: number;
  total_laps: number;
  safety_car_laps: SafetyCarWindow[];
  drivers: GapDriver[];
}

interface GapToLeaderChartProps {
  data: GapToLeaderData;
}

const SC_COLORS: Record<SafetyCarWindow["type"], string> = {
  SC: "rgba(234,179,8,0.15)",
  VSC: "rgba(249,115,22,0.15)",
  RED: "rgba(239,68,68,0.20)",
};

const SC_LABELS: Record<SafetyCarWindow["type"], string> = {
  SC: "Safety Car",
  VSC: "Virtual SC",
  RED: "Red Flag",
};

const SC_BORDER: Record<SafetyCarWindow["type"], string> = {
  SC: "rgba(234,179,8,0.60)",
  VSC: "rgba(249,115,22,0.60)",
  RED: "rgba(239,68,68,0.70)",
};

/** Cap lapped-driver gaps for rendering; avoids a 999 s axis. */
const GAP_RENDER_CAP = 120;

export function GapToLeaderChart({ data }: GapToLeaderChartProps) {
  const [hiddenDrivers, setHiddenDrivers] = useState<Set<string>>(new Set());
  const [hoveredDriver, setHoveredDriver] = useState<string | null>(null);

  const toggleDriver = (abbr: string) => {
    setHiddenDrivers((prev) => {
      const next = new Set(prev);
      next.has(abbr) ? next.delete(abbr) : next.add(abbr);
      return next;
    });
  };

  // ── Chart geometry ─────────────────────────────────────────────────────────
  const SVG_W = 900;
  const SVG_H = 400;
  const MARGIN = { top: 20, right: 20, bottom: 36, left: 54 };
  const chartW = SVG_W - MARGIN.left - MARGIN.right;
  const chartH = SVG_H - MARGIN.top - MARGIN.bottom;

  const totalLaps = data.total_laps || 1;

  // Max gap across all visible drivers, capped
  const maxGap = useMemo(() => {
    let m = 0;
    for (const d of data.drivers) {
      if (hiddenDrivers.has(d.driver)) continue;
      for (const v of Object.values(d.gaps_s)) {
        const capped = Math.min(v, GAP_RENDER_CAP);
        if (capped > m) m = capped;
      }
    }
    return m > 0 ? m : 10;
  }, [data.drivers, hiddenDrivers]);

  const xScale = (lap: number) => (lap / totalLaps) * chartW;
  const yScale = (gap: number) => chartH - (Math.min(gap, GAP_RENDER_CAP) / maxGap) * chartH;

  // X-axis ticks every 10 laps
  const xTicks: number[] = [];
  for (let l = 0; l <= totalLaps; l += 10) xTicks.push(l);

  // Y-axis ticks
  const yTickCount = 5;
  const yTicks: number[] = [];
  for (let i = 0; i <= yTickCount; i++) {
    yTicks.push(Math.round((maxGap / yTickCount) * i));
  }

  return (
    <div className="w-full space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
          <Activity size={18} className="text-blue-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white tracking-wide">
            Gap to Leader
          </h3>
          <p className="text-xs text-gray-500">
            {data.event} · {data.year} · {totalLaps} laps
          </p>
        </div>
      </div>

      {/* SC / VSC legend */}
      {data.safety_car_laps.length > 0 && (
        <div className="flex flex-wrap gap-3 text-xs">
          {(["SC", "VSC", "RED"] as const).filter((t) =>
            data.safety_car_laps.some((s) => s.type === t)
          ).map((type) => (
            <span
              key={type}
              className="flex items-center gap-1.5 px-2 py-1 rounded"
              style={{ background: SC_COLORS[type], border: `1px solid ${SC_BORDER[type]}` }}
            >
              {type === "RED" ? (
                <AlertTriangle size={12} className="text-red-400" />
              ) : (
                <Pause size={12} className="text-yellow-400" />
              )}
              <span className="text-gray-300">{SC_LABELS[type]}</span>
            </span>
          ))}
        </div>
      )}

      {/* SVG Chart */}
      <div className="rounded-xl border border-white/5 bg-black/30 p-3 overflow-x-auto">
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          className="w-full"
          style={{ minWidth: 480 }}
          aria-label="Gap to leader chart"
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {/* SC / VSC shaded bands */}
            {data.safety_car_laps.map((sc, i) => (
              <rect
                key={i}
                x={xScale(sc.start_lap - 1)}
                y={0}
                width={xScale(sc.end_lap) - xScale(sc.start_lap - 1)}
                height={chartH}
                fill={SC_COLORS[sc.type]}
                stroke={SC_BORDER[sc.type]}
                strokeWidth={0.5}
              />
            ))}

            {/* Grid lines */}
            {yTicks.map((v) => (
              <line
                key={v}
                x1={0}
                x2={chartW}
                y1={yScale(v)}
                y2={yScale(v)}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth={1}
              />
            ))}

            {/* Driver lines */}
            {data.drivers.map((driver) => {
              if (hiddenDrivers.has(driver.driver)) return null;
              const laps = Object.entries(driver.gaps_s)
                .map(([l, g]) => ({ lap: parseInt(l), gap: g }))
                .sort((a, b) => a.lap - b.lap);
              if (laps.length === 0) return null;

              const pathD = laps
                .map((p, idx) =>
                  `${idx === 0 ? "M" : "L"}${xScale(p.lap)},${yScale(p.gap)}`
                )
                .join(" ");

              const isHovered = hoveredDriver === driver.driver;

              return (
                <path
                  key={driver.driver}
                  d={pathD}
                  fill="none"
                  stroke={driver.color}
                  strokeWidth={isHovered ? 2.5 : 1.2}
                  strokeOpacity={
                    hoveredDriver === null ? 0.85 : isHovered ? 1 : 0.2
                  }
                  style={{ transition: "stroke-opacity 0.15s, stroke-width 0.15s" }}
                />
              );
            })}

            {/* X axis */}
            <line x1={0} x2={chartW} y1={chartH} y2={chartH} stroke="rgba(255,255,255,0.15)" />
            {xTicks.map((l) => (
              <g key={l} transform={`translate(${xScale(l)},${chartH})`}>
                <line y2={4} stroke="rgba(255,255,255,0.15)" />
                <text y={16} textAnchor="middle" fill="#6b7280" fontSize={10}>
                  {l}
                </text>
              </g>
            ))}
            <text
              x={chartW / 2}
              y={chartH + 32}
              textAnchor="middle"
              fill="#6b7280"
              fontSize={10}
            >
              Lap
            </text>

            {/* Y axis */}
            <line x1={0} x2={0} y1={0} y2={chartH} stroke="rgba(255,255,255,0.15)" />
            {yTicks.map((v) => (
              <g key={v} transform={`translate(0,${yScale(v)})`}>
                <line x2={-4} stroke="rgba(255,255,255,0.15)" />
                <text x={-8} textAnchor="end" dominantBaseline="middle" fill="#6b7280" fontSize={10}>
                  {v}s
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div>

      {/* Driver toggles */}
      <div className="flex flex-wrap gap-2">
        {data.drivers.map((d) => {
          const hidden = hiddenDrivers.has(d.driver);
          return (
            <button
              key={d.driver}
              onClick={() => toggleDriver(d.driver)}
              onMouseEnter={() => setHoveredDriver(d.driver)}
              onMouseLeave={() => setHoveredDriver(null)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs font-mono border transition-opacity ${
                hidden ? "opacity-30" : "opacity-100"
              }`}
              style={{
                borderColor: `${d.color}50`,
                background: `${d.color}10`,
              }}
              aria-pressed={!hidden}
              title={`${hidden ? "Show" : "Hide"} ${d.driver}`}
            >
              <span
                className="w-2 h-2 rounded-full inline-block"
                style={{ background: hidden ? "#555" : d.color }}
              />
              <span className="text-gray-200">{d.driver}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

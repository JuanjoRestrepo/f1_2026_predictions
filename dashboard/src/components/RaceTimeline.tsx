"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";

interface DriverData {
  driver: string;
  team: string;
  color: string;
  positions: Record<string, number>;
}

interface LapPositionData {
  event: string;
  year: number;
  total_laps: number;
  drivers: DriverData[];
}

interface RaceTimelineProps {
  data: LapPositionData;
}

interface TooltipPayload {
  driver: string;
  position: number;
  team: string;
}

// Build per-lap rows: [{ lap: 1, RUS: 1, ANT: 3, ... }, ...]
function buildChartData(drivers: DriverData[], totalLaps: number) {
  const rows = [];
  for (let lap = 1; lap <= totalLaps; lap++) {
    const row: Record<string, number | string> = { lap };
    for (const d of drivers) {
      const pos = d.positions[lap.toString()];
      if (pos !== undefined) row[d.driver] = pos;
    }
    rows.push(row);
  }
  return rows;
}

const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: number;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const sorted = [...payload].sort((a, b) => a.value - b.value);

  return (
    <div className="rounded-lg border border-white/10 bg-[#1a1a2e] p-3 shadow-2xl text-xs">
      <p className="font-bold text-white mb-2 border-b border-white/10 pb-1">
        Lap {label}
      </p>
      {sorted.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 py-0.5">
          <span
            className="h-2 w-2 flex-shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-gray-300 w-8 font-mono">{entry.name}</span>
          <span className="text-white font-bold">P{entry.value}</span>
        </div>
      ))}
    </div>
  );
};

export function RaceTimeline({ data }: RaceTimelineProps) {
  const [activeDriver, setActiveDriver] = useState<string | null>(null);
  const chartData = buildChartData(data.drivers, data.total_laps);

  return (
    <div className="w-full">
      <div className="mb-4">
        <p className="text-xs text-gray-400 leading-relaxed">
          Coloured lines show lap-by-lap positions for the top 10 drivers.
          <span className="text-gray-500"> Hover a line to inspect positions.</span>
        </p>
      </div>

      <ResponsiveContainer width="100%" height={340}>
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 16, left: -24, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="lap"
            stroke="#555"
            tick={{ fill: "#666", fontSize: 10 }}
            label={{ value: "Lap", position: "insideBottom", offset: -2, fill: "#555", fontSize: 11 }}
          />
          <YAxis
            reversed
            domain={[1, 10]}
            ticks={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
            stroke="#555"
            tick={{ fill: "#666", fontSize: 10 }}
            label={{ value: "Position", angle: -90, position: "insideLeft", fill: "#555", fontSize: 11 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: "11px", paddingTop: "12px" }}
            formatter={(value) => (
              <span style={{ color: "#aaa" }}>{value}</span>
            )}
          />

          {data.drivers.map((d) => (
            <Line
              key={d.driver}
              type="monotone"
              dataKey={d.driver}
              stroke={d.color}
              strokeWidth={activeDriver === d.driver ? 3 : activeDriver ? 1 : 2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              opacity={activeDriver && activeDriver !== d.driver ? 0.2 : 1}
              onMouseEnter={() => setActiveDriver(d.driver)}
              onMouseLeave={() => setActiveDriver(null)}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

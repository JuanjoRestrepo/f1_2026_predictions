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
  lineStyle?: "solid" | "dashed";
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
  payload?: Array<{ name: string; value: number; color: string; strokeDasharray?: string | number }>;
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
            style={{ 
              backgroundColor: entry.color,
              border: entry.strokeDasharray && entry.strokeDasharray !== "0" ? "1px dashed white" : "none" 
            }}
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
      <div className="mb-4 flex justify-between items-end">
        <div className="space-y-1">
          <p className="text-xs text-gray-400 leading-relaxed max-w-md">
            Interactive visualization of the full 22-driver grid. 
            <span className="text-indigo-400 font-medium"> Solid/Dashed lines differentiate teammates.</span>
          </p>
        </div>
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-wider">
          Lap-by-Lap Telemetry
        </div>
      </div>

      <div className="rounded-xl bg-black/20 p-4 border border-white/5">
        <ResponsiveContainer width="100%" height={480}>
          <LineChart
            data={chartData}
            margin={{ top: 10, right: 10, left: -25, bottom: 0 }}
          >
            <CartesianGrid 
              strokeDasharray="3 3" 
              stroke="rgba(255,255,255,0.03)" 
              vertical={false}
            />
            <XAxis
              dataKey="lap"
              stroke="#444"
              tick={{ fill: "#666", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              interval={4}
            />
            <YAxis
              reversed
              domain={[1, 22]}
              ticks={[1, 5, 10, 15, 20, 22]}
              stroke="#444"
              tick={{ fill: "#666", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip 
              content={<CustomTooltip />} 
              cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1 }}
            />
            
            <Legend
              verticalAlign="bottom"
              height={60}
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: "10px", paddingTop: "20px", opacity: 0.8 }}
              formatter={(value) => (
                <span 
                  className="cursor-pointer hover:text-white transition-colors"
                  onMouseEnter={() => setActiveDriver(value)}
                  onMouseLeave={() => setActiveDriver(null)}
                >
                  {value}
                </span>
              )}
            />

            {data.drivers.map((d) => {
              const lastLapPos = d.positions[data.total_laps.toString()] || 22;
              const isTop10 = lastLapPos <= 10;
              const isHovered = activeDriver === d.driver;
              const hasFocus = activeDriver !== null;

              let opacity = 1;
              if (hasFocus) {
                opacity = isHovered ? 1 : 0.1;
              } else {
                opacity = isTop10 ? 0.8 : 0.35;
              }

              return (
                <Line
                  key={d.driver}
                  type="monotone"
                  dataKey={d.driver}
                  stroke={d.color || "#888"}
                  strokeDasharray={d.lineStyle === "dashed" ? "5 5" : "0"}
                  strokeWidth={isHovered ? 3 : isTop10 ? 2 : 0.8}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                  opacity={opacity}
                  onMouseEnter={() => setActiveDriver(d.driver)}
                  onMouseLeave={() => setActiveDriver(null)}
                  connectNulls
                  animationDuration={800}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

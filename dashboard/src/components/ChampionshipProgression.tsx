"use client";

import { useState } from "react";
import { Trophy, Users, Building2 } from "lucide-react";

interface ChampionshipDriver {
  position: number;
  driver: string;
  team: string;
  color: string;
  points: number;
}

interface ChampionshipConstructor {
  position: number;
  team: string;
  color: string;
  points: number;
}

interface ChampionshipStandingsData {
  event: string;
  year: number;
  round: number;
  drivers: ChampionshipDriver[];
  constructors: ChampionshipConstructor[];
}

interface ChampionshipProgressionProps {
  data: ChampionshipStandingsData;
}

type TabId = "drivers" | "constructors";

const MEDAL_COLORS: Record<number, string> = {
  1: "#FFD700",
  2: "#C0C0C0",
  3: "#CD7F32",
};

/** Normalise points to a bar width percentage of the leader's total. */
function barWidth(pts: number, maxPts: number): string {
  if (maxPts <= 0) return "0%";
  return `${Math.max(2, (pts / maxPts) * 100)}%`;
}

export function ChampionshipProgression({ data }: ChampionshipProgressionProps) {
  const [activeTab, setActiveTab] = useState<TabId>("drivers");

  const sortedDrivers = [...data.drivers].sort((a, b) => a.position - b.position);
  const sortedConstructors = [...data.constructors].sort((a, b) => a.position - b.position);

  const maxDriverPts = sortedDrivers[0]?.points ?? 0;
  const maxConstructorPts = sortedConstructors[0]?.points ?? 0;

  const tabs: { id: TabId; label: string; icon: typeof Users }[] = [
    { id: "drivers", label: "Drivers", icon: Users },
    { id: "constructors", label: "Constructors", icon: Building2 },
  ];

  return (
    <div className="w-full space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="p-2 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
          <Trophy size={18} className="text-yellow-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white tracking-wide">
            Championship Standings
          </h3>
          <p className="text-xs text-gray-500">
            After {data.event} · R{data.round} · {data.year}
          </p>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 bg-black/40 rounded-lg border border-white/5 w-fit">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all ${
              activeTab === id
                ? "bg-white/10 text-white shadow"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* Drivers standings */}
      {activeTab === "drivers" && (
        <div className="space-y-1.5">
          {sortedDrivers.map((entry) => (
            <div
              key={entry.driver}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/5 bg-black/30"
            >
              {/* Position */}
              <span
                className="w-6 text-center text-sm font-bold flex-shrink-0"
                style={{ color: MEDAL_COLORS[entry.position] ?? "#6b7280" }}
              >
                {entry.position}
              </span>

              {/* Driver code + team */}
              <div className="w-24 flex-shrink-0">
                <span
                  className="text-sm font-bold font-mono tracking-wider"
                  style={{ color: entry.color }}
                >
                  {entry.driver}
                </span>
                <p className="text-xs text-gray-500 truncate leading-tight">{entry.team}</p>
              </div>

              {/* Points bar */}
              <div className="flex-1 relative h-2 bg-white/5 rounded overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded transition-all duration-500"
                  style={{
                    width: barWidth(entry.points, maxDriverPts),
                    background: entry.color,
                    opacity: 0.7,
                  }}
                />
              </div>

              {/* Points value */}
              <span className="text-xs font-mono text-gray-200 w-14 text-right flex-shrink-0">
                {entry.points.toFixed(0)} pts
              </span>
            </div>
          ))}
          {sortedDrivers.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-4">
              No driver standings data available.
            </p>
          )}
        </div>
      )}

      {/* Constructors standings */}
      {activeTab === "constructors" && (
        <div className="space-y-1.5">
          {sortedConstructors.map((entry) => (
            <div
              key={entry.team}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/5 bg-black/30"
            >
              {/* Position */}
              <span
                className="w-6 text-center text-sm font-bold flex-shrink-0"
                style={{ color: MEDAL_COLORS[entry.position] ?? "#6b7280" }}
              >
                {entry.position}
              </span>

              {/* Team name + color swatch */}
              <div className="w-36 flex-shrink-0 flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ background: entry.color }}
                />
                <span className="text-sm font-medium text-white truncate">{entry.team}</span>
              </div>

              {/* Points bar */}
              <div className="flex-1 relative h-2 bg-white/5 rounded overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded transition-all duration-500"
                  style={{
                    width: barWidth(entry.points, maxConstructorPts),
                    background: entry.color,
                    opacity: 0.7,
                  }}
                />
              </div>

              {/* Points value */}
              <span className="text-xs font-mono text-gray-200 w-14 text-right flex-shrink-0">
                {entry.points.toFixed(0)} pts
              </span>
            </div>
          ))}
          {sortedConstructors.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-4">
              No constructor standings data available.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

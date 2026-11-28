"use client";

import { useState } from "react";
import { Clock, Wrench, ChevronDown, ChevronUp } from "lucide-react";

interface PitStopEntry {
  driver: string;
  lap: number;
  pit_duration_s: number;
  stationary_s: number;
}

interface PitStopTeam {
  team: string;
  color: string;
  stops: PitStopEntry[];
}

interface PitStopEfficiencyData {
  event: string;
  year: number;
  teams: PitStopTeam[];
}

interface PitStopEfficiencyProps {
  data: PitStopEfficiencyData;
}

/** Maximum pit duration for normalising bar widths. */
const BAR_MAX_S = 60;

function formatDuration(s: number): string {
  return `${s.toFixed(1)}s`;
}

export function PitStopEfficiency({ data }: PitStopEfficiencyProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleTeam = (team: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(team) ? next.delete(team) : next.add(team);
      return next;
    });
  };

  // Compute team-level averages for the summary bar
  const teamAverages = data.teams.map((t) => {
    const avgPit =
      t.stops.reduce((sum, s) => sum + s.pit_duration_s, 0) / (t.stops.length || 1);
    const avgStat =
      t.stops.reduce((sum, s) => sum + s.stationary_s, 0) / (t.stops.length || 1);
    return { team: t.team, color: t.color, avgPit, avgStat, stopsCount: t.stops.length };
  });

  // Sort teams by average pit duration ascending (fastest first)
  const sorted = [...teamAverages].sort((a, b) => a.avgPit - b.avgPit);

  return (
    <div className="w-full space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="p-2 bg-orange-500/10 rounded-lg border border-orange-500/20">
          <Wrench size={18} className="text-orange-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white tracking-wide">
            Pit Stop Efficiency
          </h3>
          <p className="text-xs text-gray-500">
            {data.event} · {data.year} · total pit lane time vs stationary stop time
          </p>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="w-8 h-2 rounded bg-white/20 inline-block" />
          Pit lane time
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-8 h-2 rounded bg-blue-400/70 inline-block" />
          Stationary time
        </span>
      </div>

      {/* Team summary bars */}
      <div className="space-y-2">
        {sorted.map(({ team, color, avgPit, avgStat, stopsCount }) => {
          const isExpanded = expanded.has(team);
          const teamData = data.teams.find((t) => t.team === team)!;
          const pitWidth = `${Math.min((avgPit / BAR_MAX_S) * 100, 100)}%`;
          const statWidth = `${Math.min((avgStat / BAR_MAX_S) * 100, 100)}%`;

          return (
            <div
              key={team}
              className="rounded-xl border border-white/5 bg-black/30 overflow-hidden"
            >
              {/* Team header row */}
              <button
                onClick={() => toggleTeam(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors"
                aria-expanded={isExpanded}
              >
                {/* Color swatch */}
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ background: color }}
                />

                {/* Team name */}
                <span className="text-sm font-medium text-white flex-1 text-left truncate">
                  {team}
                </span>

                {/* Stop count */}
                <span className="text-xs text-gray-500 flex-shrink-0">
                  {stopsCount} stop{stopsCount !== 1 ? "s" : ""}
                </span>

                {/* Bars */}
                <div className="flex-1 max-w-xs relative h-5 flex flex-col justify-center gap-0.5">
                  {/* Outer: full pit lane */}
                  <div className="relative h-2 rounded bg-white/10 overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0 rounded"
                      style={{ width: pitWidth, background: `${color}50` }}
                    />
                  </div>
                  {/* Inner: stationary */}
                  <div className="relative h-1.5 rounded bg-white/5 overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0 rounded bg-blue-400/70"
                      style={{ width: statWidth }}
                    />
                  </div>
                </div>

                {/* Avg time labels */}
                <div className="flex-shrink-0 flex gap-3 items-center text-xs font-mono">
                  <span className="text-gray-300">{formatDuration(avgPit)}</span>
                  <span className="text-blue-400">{formatDuration(avgStat)}</span>
                  <Clock size={12} className="text-gray-600" />
                  {isExpanded ? (
                    <ChevronUp size={14} className="text-gray-500" />
                  ) : (
                    <ChevronDown size={14} className="text-gray-500" />
                  )}
                </div>
              </button>

              {/* Expanded per-driver stops */}
              {isExpanded && (
                <div className="border-t border-white/5 px-4 pb-3 pt-2 space-y-1.5">
                  <div className="grid grid-cols-4 text-xs text-gray-500 uppercase tracking-wider mb-1">
                    <span>Driver</span>
                    <span className="text-right">Lap</span>
                    <span className="text-right">Pit lane</span>
                    <span className="text-right">Stationary</span>
                  </div>
                  {teamData.stops.map((stop, idx) => (
                    <div
                      key={idx}
                      className="grid grid-cols-4 text-xs font-mono py-1 border-b border-white/[0.03] last:border-0"
                    >
                      <span
                        className="font-semibold"
                        style={{ color }}
                      >
                        {stop.driver}
                      </span>
                      <span className="text-right text-gray-400">{stop.lap}</span>
                      <span className="text-right text-gray-300">
                        {formatDuration(stop.pit_duration_s)}
                      </span>
                      <span className="text-right text-blue-400">
                        {formatDuration(stop.stationary_s)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import { Fuel, Timer, Lightbulb } from "lucide-react";

interface Stint {
  stint: number;
  compound: string;
  laps: number;
  color: string;
}

interface DriverTyreData {
  driver: string;
  team: string;
  stints: Stint[];
}

interface TyreIntelligenceData {
  gp: string;
  year: number;
  winning_strategy: string;
  avg_pit_stop: string;
  proven_strategy_insight: string;
  drivers: DriverTyreData[];
}

interface TyreIntelligenceProps {
  data: TyreIntelligenceData;
}

export function TyreIntelligence({ data }: TyreIntelligenceProps) {
  const totalLaps = 57;

  return (
    <div className="w-full space-y-6">
      {/* Header Stats */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg bg-black/30 border border-white/5 p-4 flex items-center gap-3 shadow-inner">
          <div className="p-2 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
            <Fuel size={18} className="text-yellow-500" />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-500">Winning Strategy</p>
            <p className="text-sm font-bold text-white">{data.winning_strategy}</p>
          </div>
        </div>
        <div className="rounded-lg bg-black/30 border border-white/5 p-4 flex items-center gap-3 shadow-inner">
          <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
            <Timer size={18} className="text-blue-500" />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gray-500">Avg Pit Stop</p>
            <p className="text-sm font-bold text-white">{data.avg_pit_stop}</p>
          </div>
        </div>
      </div>

      {/* Strategy Bars */}
      <div className="space-y-4">
        {data.drivers.map((driver) => (
          <div key={driver.driver} className="space-y-1.5">
            <div className="flex justify-between items-center px-1">
              <span className="text-xs font-bold text-gray-300 w-8">{driver.driver}</span>
              <div className="flex gap-2">
                {driver.stints.map((s, idx) => (
                  <span key={idx} className="text-[10px] text-gray-500">
                    S{s.stint}: {s.compound} ({s.laps})
                  </span>
                ))}
              </div>
            </div>
            <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden flex shadow-sm">
              {driver.stints.map((stint, idx) => {
                const width = (stint.laps / totalLaps) * 100;
                return (
                  <div
                    key={idx}
                    style={{ 
                      width: `${width}%`, 
                      backgroundColor: stint.color,
                      opacity: stint.compound === "HARD" ? 0.9 : 1
                    }}
                    className={`h-full border-r border-black/20 last:border-0 relative group`}
                    title={`${stint.compound} - ${stint.laps} laps`}
                  >
                    <div className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Strategic Insight */}
      <div className="rounded-xl bg-blue-500/5 border border-blue-500/10 p-5 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-5">
           <Lightbulb size={64} className="text-blue-400" />
        </div>
        <div className="flex items-start gap-3 relative z-10">
          <Lightbulb size={20} className="text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-blue-400 mb-2">Strategy Intelligence Report</p>
            <p className="text-sm text-gray-300 leading-relaxed italic">
              "{data.proven_strategy_insight}"
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

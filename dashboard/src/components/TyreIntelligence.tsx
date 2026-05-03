"use client";

import { useState } from "react";
import { Fuel, Timer, Lightbulb, Search, MousePointer2 } from "lucide-react";

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
  const [activeDriver, setActiveDriver] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const totalLaps = 57;

  const filteredDrivers = data.drivers.filter(d => 
    d.driver.toLowerCase().includes(search.toLowerCase()) || 
    d.team.toLowerCase().includes(search.toLowerCase())
  );

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

      {/* Driver List with Search */}
      <div className="space-y-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <MousePointer2 size={12} className="text-f1red" />
            <span>Click a driver to highlight</span>
          </div>
          <div className="relative group">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-f1red transition-colors" />
            <input 
              type="text" 
              placeholder="Filter drivers..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-md py-1 pl-7 pr-3 text-[10px] text-white focus:outline-none focus:border-f1red transition-all w-32 md:w-40"
            />
          </div>
        </div>

        <div className="max-h-[360px] overflow-y-auto pr-2 custom-scrollbar space-y-3">
          {filteredDrivers.map((driver) => {
            const isHighlighted = activeDriver === driver.driver;
            const isDimmed = activeDriver && activeDriver !== driver.driver;

            return (
              <div 
                key={driver.driver} 
                onClick={() => setActiveDriver(activeDriver === driver.driver ? null : driver.driver)}
                className={`space-y-1.5 cursor-pointer transition-all duration-300 ${
                  isHighlighted ? "scale-[1.02] translate-x-1" : ""
                } ${isDimmed ? "opacity-30 blur-[0.5px]" : "opacity-100"}`}
              >
                <div className="flex justify-between items-center px-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold font-mono ${isHighlighted ? "text-f1red" : "text-gray-300"}`}>
                      {driver.driver}
                    </span>
                    {isHighlighted && (
                      <span className="text-[10px] text-gray-500 uppercase tracking-tighter">{driver.team}</span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {driver.stints.map((s, idx) => (
                      <span key={idx} className={`text-[9px] uppercase font-medium ${
                        s.compound === "SOFT" ? "text-red-500" :
                        s.compound === "MEDIUM" ? "text-yellow-500" :
                        "text-white"
                      }`}>
                        {s.compound[0]}
                        <span className="text-gray-600 ml-0.5">({s.laps})</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div className={`h-2 w-full bg-white/5 rounded-full overflow-hidden flex transition-all ${
                  isHighlighted ? "ring-1 ring-f1red/30 shadow-[0_0_10px_rgba(225,6,0,0.1)]" : ""
                }`}>
                  {driver.stints.map((stint, idx) => {
                    const width = (stint.laps / totalLaps) * 100;
                    return (
                      <div
                        key={idx}
                        style={{ 
                          width: `${width}%`, 
                          backgroundColor: stint.color,
                        }}
                        className="h-full border-r border-black/20 last:border-0 relative"
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Strategic Insight */}
      <div className="rounded-xl bg-blue-500/5 border border-blue-500/10 p-5 relative overflow-hidden transition-all hover:bg-blue-500/10 group">
        <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
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

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.02);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(225, 6, 0, 0.5);
        }
      `}</style>
    </div>
  );
}

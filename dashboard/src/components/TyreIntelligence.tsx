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
  fullName: string;
  team: string;
  stints: Stint[];
}

interface TyreIntelligenceData {
  gp: string;
  year: number;
  total_laps?: number;
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
  const totalLaps = data.total_laps || 57; // Dynamic total laps or fallback

  // Flexible search: match driver code, full name, or team
  const filteredDrivers = data.drivers.filter(d => {
    const s = search.toLowerCase();
    return (
      d.driver.toLowerCase().includes(s) || 
      (d.fullName || '').toLowerCase().includes(s) ||
      d.team.toLowerCase().includes(s)
    );
  });

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
            <span>Click to highlight</span>
          </div>
          <div className="relative group">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-f1red transition-colors" />
            <input 
              type="text" 
              placeholder="Search Lando, Norris, etc..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-md py-1.5 pl-7 pr-3 text-[10px] text-white placeholder:text-gray-600 focus:outline-none focus:border-f1red transition-all w-40 md:w-56"
            />
          </div>
        </div>

        <div className="max-h-[420px] overflow-y-auto pr-2 custom-scrollbar space-y-5">
          {filteredDrivers.map((driver) => {
            const isHighlighted = activeDriver === driver.driver;
            const isDimmed = activeDriver && activeDriver !== driver.driver;

            return (
              <div 
                key={driver.driver} 
                onClick={() => setActiveDriver(activeDriver === driver.driver ? null : driver.driver)}
                className={`space-y-2 cursor-pointer transition-all duration-300 ${
                  isHighlighted ? "scale-[1.01]" : ""
                } ${isDimmed ? "opacity-30 blur-[0.3px]" : "opacity-100"}`}
              >
                <div className="flex justify-between items-center px-1">
                  <div className="flex items-baseline gap-2">
                    <span className={`text-xs font-black font-mono ${isHighlighted ? "text-f1red" : "text-gray-200"}`}>
                      {driver.driver}
                    </span>
                    <span className="text-[9px] text-gray-500 uppercase font-bold tracking-tighter">
                      {driver.team}
                    </span>
                  </div>
                  
                  <div className="flex gap-1.5">
                    {driver.stints.map((s, idx) => (
                      <div key={idx} className="flex items-center gap-1 bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: s.color }} />
                        <span className="text-[8px] font-bold text-gray-300">{s.compound[0]}</span>
                        <span className="text-[8px] font-medium text-gray-500">{s.laps}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className={`h-3 w-full bg-white/5 rounded-sm overflow-hidden flex border border-white/5 transition-all ${
                  isHighlighted ? "ring-1 ring-white/20 shadow-lg" : ""
                }`}>
                  {driver.stints.map((stint, idx) => {
                    const width = (stint.laps / totalLaps) * 100;
                    return (
                      <div
                        key={idx}
                        style={{ 
                          width: `${width}%`, 
                          backgroundColor: stint.color,
                          backgroundImage: `linear-gradient(to bottom, rgba(255,255,255,0.1), transparent)`
                        }}
                        className="h-full border-r border-black/30 last:border-0 relative group/stint"
                      >
                        <div className="absolute inset-0 bg-white/0 group-hover/stint:bg-white/10 transition-colors" />
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {filteredDrivers.length === 0 && (
            <div className="py-8 text-center">
              <p className="text-xs text-gray-500 italic">No drivers matching "{search}"</p>
            </div>
          )}
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

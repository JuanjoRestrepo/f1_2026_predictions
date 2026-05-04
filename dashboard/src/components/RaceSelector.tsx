"use client";

import { useRouter } from "next/router";
import { ChevronDown, Calendar } from "lucide-react";
import type { RaceInfo } from "../utils/fileReader";

interface RaceSelectorProps {
  currentRound: number;
  availableRaces: RaceInfo[];
}

export function RaceSelector({ currentRound, availableRaces }: RaceSelectorProps) {
  const router = useRouter();

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const round = e.target.value;
    router.push(`/race/${round}`);
  };

  return (
    <div className="relative flex items-center gap-2 bg-black/20 hover:bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 transition-all group">
      <Calendar size={14} className="text-f1red" />
      <select
        value={currentRound}
        onChange={handleChange}
        className="bg-transparent text-xs font-bold text-gray-200 focus:outline-none cursor-pointer appearance-none pr-6"
      >
        {availableRaces.map((race) => (
          <option key={race.round} value={race.round} className="bg-f1dark text-white">
            {race.name}
          </option>
        ))}
      </select>
      <ChevronDown size={12} className="absolute right-3 text-gray-500 pointer-events-none group-hover:text-f1red transition-colors" />
    </div>
  );
}

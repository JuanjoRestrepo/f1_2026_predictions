"use client";

import { useRouter } from "next/router";
import { ChevronDown, Calendar, Lock } from "lucide-react";
import type { RaceInfo } from "../utils/fileReader";

interface RaceSelectorProps {
  currentRound: number;
  /** Races that have completed simulation reports and a built page. */
  availableRaces: RaceInfo[];
  /**
   * The full season calendar. Used to show all rounds in the dropdown so the
   * user can see the full schedule. Rounds that are not in `availableRaces`
   * are displayed but disabled — clicking them would previously cause a Vercel
   * 404 because Next.js only builds `getStaticPaths` entries for rounds with
   * actual report data.
   */
  fullCalendar: RaceInfo[];
}

export function RaceSelector({ currentRound, availableRaces, fullCalendar }: RaceSelectorProps) {
  const router = useRouter();
  const availableRounds = new Set(availableRaces.map((r) => r.round));

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const round = parseInt(e.target.value, 10);
    // Guard: only navigate to rounds that have a built page. The disabled
    // attribute on <option> prevents this in most browsers, but we double-check
    // here for programmatic robustness.
    if (availableRounds.has(round)) {
      void router.push(`/race/${round}`);
    }
  };

  // Use the full calendar for the dropdown, falling back to availableRaces if
  // the full calendar hasn't been synced yet (graceful degradation).
  const displayCalendar = fullCalendar.length > 0 ? fullCalendar : availableRaces;

  return (
    <div className="relative flex items-center gap-2 bg-black/20 hover:bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 transition-all group">
      <Calendar size={14} className="text-f1red" />
      <select
        value={currentRound}
        onChange={handleChange}
        className="bg-transparent text-xs font-bold text-gray-200 focus:outline-none cursor-pointer appearance-none pr-6"
        aria-label="Select a race"
      >
        {displayCalendar.map((race) => {
          const isAvailable = availableRounds.has(race.round);
          return (
            <option
              key={race.round}
              value={race.round}
              disabled={!isAvailable}
              className={`bg-f1dark ${isAvailable ? "text-white" : "text-gray-500"}`}
            >
              {isAvailable ? "" : "🔒 "}R{race.round} — {race.name}
            </option>
          );
        })}
      </select>
      <ChevronDown
        size={12}
        className="absolute right-3 text-gray-500 pointer-events-none group-hover:text-f1red transition-colors"
      />
      {/* Visual indicator that this round is locked (upcoming) */}
      {!availableRounds.has(currentRound) && (
        <Lock size={12} className="text-yellow-500/70" aria-label="Simulation pending" />
      )}
    </div>
  );
}

import type { PredictionRow, ActualResult } from "../utils/fileReader";

interface PredictionsTableProps {
  data: (PredictionRow | ActualResult)[];
  view: "predicted" | "actual";
}

const TEAM_COLORS: Record<string, string> = {
  Mercedes: "bg-[#00d2be]",
  Ferrari: "bg-[#dc0000]",
  McLaren: "bg-[#ff8700]",
  "Red Bull Racing": "bg-[#0600ef]",
  "Aston Martin": "bg-[#006f62]",
  Alpine: "bg-[#0090ff]",
  Williams: "bg-[#005aff]",
  "Racing Bulls": "bg-[#4e7c9b]",
  Haas: "bg-[#b6babd]",
  "Haas F1 Team": "bg-[#b6babd]",
  Audi: "bg-[#a5a5a5]",
  Cadillac: "bg-[#ffffff]",
};

function getTeamColor(team: string) {
  return TEAM_COLORS[team] ?? "bg-gray-500";
}

export function PredictionsTable({ data, view }: PredictionsTableProps) {
  return (
    <div className="w-full">
      <table className="w-full text-left text-sm">
        <thead className="text-xs md:text-sm uppercase tracking-widest text-gray-500 border-b border-white/5">
          <tr>
            <th className="px-4 py-3 font-medium w-12">Pos</th>
            <th className="px-4 py-3 font-medium">Driver</th>
            <th className="px-4 py-3 font-medium">Team</th>
            <th className="px-4 py-3 font-medium text-right">Time / Gap</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {data.map((row, idx) => {
            const isPredicted = view === "predicted";
            const driver = isPredicted ? (row as PredictionRow).Driver : (row as ActualResult).driver;
            const team = isPredicted ? (row as PredictionRow).Team : (row as ActualResult).team;
            const position = isPredicted 
              ? (row as PredictionRow).predicted_position 
              : (row as ActualResult).position;
            
            // For predicted, we show the laptime delta. For actual, we show the time/gap string.
            const displayTime = isPredicted
              ? (idx === 0 ? "1:23:06.801" : `+${parseFloat((row as PredictionRow).predicted_laptime_stack_s || (row as PredictionRow).predicted_laptime_xgb_s).toFixed(3)}s`)
              : (row as ActualResult).time || (row as ActualResult).gap;

            return (
              <tr key={idx} className="hover:bg-white/5 transition-colors group">
                <td className="px-4 py-4 whitespace-nowrap">
                  <span className={`text-xs md:text-sm font-bold ${
                    idx === 0 ? "text-yellow-500" :
                    idx === 1 ? "text-gray-300" :
                    idx === 2 ? "text-amber-600" :
                    "text-gray-500"
                  }`}>
                    P{position || idx + 1}
                  </span>
                </td>

                <td className="px-4 py-4 whitespace-nowrap">
                  <span className="text-sm md:text-base font-bold text-white group-hover:text-red-400 transition-colors">
                    {driver}
                  </span>
                </td>

                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 flex-shrink-0 rounded-full ${getTeamColor(team)}`} />
                    <span className="text-gray-400 text-xs md:text-sm truncate">{team}</span>
                  </div>
                </td>

                <td className="px-4 py-4 whitespace-nowrap text-right">
                  <span className="font-mono text-sm md:text-base text-gray-300">
                    {displayTime}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

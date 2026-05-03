import type { PredictionRow } from "../utils/fileReader";

interface PredictionsTableProps {
  predictions: PredictionRow[];
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
  Audi: "bg-[#a5a5a5]",
};

function getTeamColor(team: string) {
  return TEAM_COLORS[team] ?? "bg-gray-500";
}

// Calculate a human-readable gap from the winner's laptime
function formatGap(winnerTime: number, driverTime: number, idx: number): string {
  if (idx === 0) return "1:23:06.801"; // Winner time placeholder
  const gapSeconds = driverTime - winnerTime;
  return `+${gapSeconds.toFixed(3)}s`;
}

export function PredictionsTable({ predictions }: PredictionsTableProps) {
  const winnerTime = predictions.length > 0
    ? parseFloat(predictions[0]!.predicted_laptime_xgb_s)
    : 0;

  return (
    <div className="w-full">
      <table className="w-full text-left text-sm">
        <thead className="text-[10px] uppercase tracking-widest text-gray-500 border-b border-white/5">
          <tr>
            <th className="px-4 py-3 font-medium w-12">Pos</th>
            <th className="px-4 py-3 font-medium">Driver</th>
            <th className="px-4 py-3 font-medium">Team</th>
            <th className="px-4 py-3 font-medium text-right">Time / Gap</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {predictions.map((row, idx) => (
            <tr key={idx} className="hover:bg-white/5 transition-colors group">
              <td className="px-4 py-4 whitespace-nowrap">
                <span className={`text-xs font-bold ${
                  idx === 0 ? "text-yellow-500" :
                  idx === 1 ? "text-gray-300" :
                  idx === 2 ? "text-amber-600" :
                  "text-gray-500"
                }`}>
                  P{row.predicted_position ?? idx + 1}
                </span>
              </td>

              <td className="px-4 py-4 whitespace-nowrap">
                <span className="font-bold text-white group-hover:text-red-400 transition-colors">
                  {row.Driver}
                </span>
              </td>

              <td className="px-4 py-4 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 flex-shrink-0 rounded-full ${getTeamColor(row.Team)}`} />
                  <span className="text-gray-400 text-xs truncate">{row.Team}</span>
                </div>
              </td>

              <td className="px-4 py-4 whitespace-nowrap text-right">
                <span className="font-mono text-sm text-gray-300">
                  {formatGap(winnerTime, parseFloat(row.predicted_laptime_xgb_s), idx)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

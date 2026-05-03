import type { PredictionRow } from "../utils/fileReader";

interface PredictionsTableProps {
  predictions: PredictionRow[];
}

function getTeamColor(abbr: string) {
  const map: Record<string, string> = {
    "RUS": "bg-[#00d2be]", // Mercedes
    "ANT": "bg-[#00d2be]", 
    "LEC": "bg-[#dc0000]", // Ferrari
    "HAM": "bg-[#dc0000]",
    "NOR": "bg-[#ff8700]", // McLaren
    "PIA": "bg-[#ff8700]",
    "VER": "bg-[#0600ef]", // Red Bull
    "HAD": "bg-[#0600ef]",
    "ALO": "bg-[#006f62]", // Aston Martin
    "STR": "bg-[#006f62]",
  };
  return map[abbr] || "bg-gray-500";
}

function getTeamName(abbr: string) {
  const map: Record<string, string> = {
    "RUS": "Mercedes",
    "ANT": "Mercedes",
    "LEC": "Ferrari",
    "HAM": "Ferrari",
    "NOR": "McLaren",
    "PIA": "McLaren",
    "VER": "Red Bull",
    "HAD": "Red Bull",
    "ALO": "Aston Martin",
    "STR": "Aston Martin",
  };
  return map[abbr] || "Team";
}

export function PredictionsTable({ predictions }: PredictionsTableProps) {
  return (
    <div className="w-full">
      <table className="w-full text-left text-sm">
        <thead className="text-[10px] uppercase tracking-widest text-f1gray border-b border-white/5">
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
                  "text-f1gray"
                }`}>
                  P{row.Predicted_Position || idx + 1}
                </span>
              </td>
              
              <td className="px-4 py-4 whitespace-nowrap">
                <div className="flex flex-col">
                  <span className="font-bold text-white group-hover:text-red-400 transition-colors">
                    {row.Abbreviation}
                  </span>
                </div>
              </td>
              
              <td className="px-4 py-4 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${getTeamColor(row.Abbreviation)}`}></span>
                  <span className="text-gray-400 text-xs">{getTeamName(row.Abbreviation)}</span>
                </div>
              </td>
              
              <td className="px-4 py-4 whitespace-nowrap text-right">
                <span className="font-mono text-sm text-gray-300">
                  {idx === 0 ? "1:23:06.801" : `+${parseFloat(row.predicted_laptime_xgb_s).toFixed(3)}s`}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

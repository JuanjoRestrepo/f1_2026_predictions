import Head from "next/head";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Trophy, Medal, Timer } from "lucide-react";
import { RaceReport } from "../components/RaceReport";
import { PredictionsTable } from "../components/PredictionsTable";
import { ViewToggle } from "../components/ViewToggle";
import { TyreIntelligence } from "../components/TyreIntelligence";
import {
  getRaceSummary,
  getRacePredictions,
  getLapPositions,
  getPredictedLapPositions,
  getActualResults,
  getTyreIntelligence,
  type PredictionRow,
  type LapPositionData,
  type ActualResult,
  type TyreIntelligenceData,
} from "../utils/fileReader";

// Recharts uses browser APIs — load client-side only
const RaceTimeline = dynamic(
  () => import("../components/RaceTimeline").then((m) => m.RaceTimeline),
  { ssr: false }
);

interface DashboardProps {
  markdownReport: string | null;
  predictions: PredictionRow[] | null;
  actualResults: ActualResult[] | null;
  lapPositions: LapPositionData | null;
  predictedLapPositions: LapPositionData | null;
  tyreData: TyreIntelligenceData | null;
}

export async function getStaticProps() {
  const year = 2026;
  const roundNum = 4;
  const eventDirName = "Miami_Grand_Prix";

  const markdownReport = getRaceSummary(year, eventDirName, roundNum);
  const predictions = getRacePredictions(year, eventDirName) ?? [];
  const actualResults = getActualResults(year, roundNum) ?? [];
  const lapPositions = getLapPositions(year, roundNum);
  const predictedLapPositions = getPredictedLapPositions(year, roundNum);
  const tyreData = getTyreIntelligence(year, roundNum);

  return {
    props: { markdownReport, predictions, actualResults, lapPositions, predictedLapPositions, tyreData },
    revalidate: 3600,
  };
}

export default function Home({ 
  markdownReport, 
  predictions, 
  actualResults, 
  lapPositions, 
  predictedLapPositions,
  tyreData 
}: DashboardProps) {
  const [tableView, setTableView] = useState<"predicted" | "actual">("predicted");
  const [chartView, setChartView] = useState<"predicted" | "actual">("actual");

  // Determine which data to show based on view
  const currentTableData = tableView === "predicted" ? (predictions ?? []) : (actualResults ?? []);
  
  // Extract top drivers
  const winner = actualResults && actualResults.length > 0 
    ? actualResults[0] 
    : (predictions && predictions.length > 0 && predictions[0] 
        ? { Driver: predictions[0].Driver, Team: predictions[0].Team } 
        : null);

  const secondPlace = actualResults && actualResults.length > 1 
    ? actualResults[1] 
    : (predictions && predictions.length > 1 && predictions[1] 
        ? { Driver: predictions[1].Driver, Team: predictions[1].Team } 
        : null);

  return (
    <>
      <Head>
        <title>F1 2026 AI Dashboard — Miami Grand Prix</title>
        <meta name="description" content="AI-Powered Formula 1 Predictions & Race Analysis" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main className="min-h-screen bg-f1darker text-gray-100 pb-16 font-sans">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

          {/* ─── Red Header Banner ─── */}
          <div className="mb-8 overflow-hidden rounded-xl bg-gradient-to-r from-f1red to-[#a00000] shadow-2xl">
            <div className="px-8 py-10">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-3xl">🏁</span>
                <h1 className="text-4xl font-extrabold tracking-tight text-white drop-shadow-md">
                  Miami Grand Prix 2026
                </h1>
              </div>
              <p className="text-red-100 font-medium tracking-wide">
                Miami · 2026-05-03 · 57 laps
              </p>
            </div>
          </div>

          {/* ─── Metric Cards ─── */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3 mb-10">
            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center shadow-lg">
              <div className="flex items-center gap-2 text-yellow-500 mb-2">
                <Trophy size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Race Winner</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {winner ? ("Driver" in winner ? winner.Driver : winner.driver) : "--"}
              </h2>
              <p className="text-sm text-gray-400">{winner ? ("Team" in winner ? winner.Team : winner.team) : ""}</p>
            </div>

            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center shadow-lg">
              <div className="flex items-center gap-2 text-gray-400 mb-2">
                <Medal size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">2nd Place</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {secondPlace ? ("Driver" in secondPlace ? secondPlace.Driver : secondPlace.driver) : "--"}
              </h2>
              <p className="text-sm text-gray-400">{secondPlace ? ("Team" in secondPlace ? secondPlace.Team : secondPlace.team) : ""}</p>
            </div>

            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center shadow-lg">
              <div className="flex items-center gap-2 text-purple-400 mb-2">
                <Timer size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Fastest Lap</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">RUS</h2>
              <p className="text-sm text-gray-400">1:27.452</p>
            </div>
          </div>

          {/* ─── Top Row: Race Timeline + Finishing Order ─── */}
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 mb-10">
            {/* Race Timeline Chart (Left) */}
            <div className="lg:col-span-7 flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-widest text-f1red">
                    Race Timeline — Position Chart
                  </h3>
                </div>
                <ViewToggle activeView={chartView} onToggle={setChartView} />
              </div>
              
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 p-6 shadow-inner mb-8">
                {chartView === "actual" ? (
                  lapPositions ? (
                    <RaceTimeline data={lapPositions} />
                  ) : (
                    <div className="flex h-64 items-center justify-center">
                      <p className="text-gray-500 text-sm italic">No actual lap data available.</p>
                    </div>
                  )
                ) : (
                  predictedLapPositions ? (
                    <RaceTimeline data={predictedLapPositions} />
                  ) : (
                    <div className="flex h-full min-h-[340px] items-center justify-center bg-black/20 rounded-lg border border-dashed border-white/10">
                      <p className="text-gray-500 text-xs italic">Simulated timeline pending.</p>
                    </div>
                  )
                )}
              </div>

              {/* Tyre Intelligence (Below Chart) */}
              <div className="mt-auto">
                <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-4">
                  Race Tyre Intelligence
                </h3>
                <div className="rounded-xl bg-f1dark border border-white/5 p-6 shadow-xl">
                  {tyreData ? (
                    <TyreIntelligence data={tyreData} />
                  ) : (
                    <p className="text-gray-500 text-sm italic">Tyre strategy data unavailable.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Finishing Order Table (Right) */}
            <div className="lg:col-span-5 flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold uppercase tracking-widest text-f1red">
                  Finishing Order
                </h3>
                <ViewToggle activeView={tableView} onToggle={setTableView} />
              </div>
              
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 overflow-hidden shadow-xl">
                {currentTableData.length > 0 ? (
                  <PredictionsTable data={currentTableData} view={tableView} />
                ) : (
                  <div className="flex h-64 items-center justify-center">
                    <p className="text-gray-500 text-sm">No data available.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ─── AI Race Analysis (full-width below) ─── */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-4">
              AI Race Analysis
            </h3>
            <div className="rounded-xl bg-f1dark border border-white/5 p-6 shadow-2xl">
              <div className="flex items-center gap-3 mb-5 border-b border-white/5 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-red-600/20 border border-red-600/30">
                  <span className="text-sm font-bold text-red-400">AI</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">Gemini 3.1 Pro</p>
                  <p className="text-xs text-gray-500">Auto-generated post-race narrative</p>
                </div>
              </div>
              {markdownReport ? (
                <RaceReport markdownContent={markdownReport} />
              ) : (
                <p className="text-gray-500 text-sm italic">No AI analysis available yet.</p>
              )}
            </div>
          </div>

        </div>
      </main>
    </>
  );
}

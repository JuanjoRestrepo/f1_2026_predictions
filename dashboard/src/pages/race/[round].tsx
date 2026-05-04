import Head from "next/head";
import dynamic from "next/dynamic";
import { useState } from "react";
import { Trophy, Medal, Timer } from "lucide-react";
import { RaceReport } from "../../components/RaceReport";
import { PredictionsTable } from "../../components/PredictionsTable";
import { ViewToggle } from "../../components/ViewToggle";
import { TyreIntelligence } from "../../components/TyreIntelligence";
import { RaceSelector } from "../../components/RaceSelector";
import {
  getRaceSummary,
  getPredictedRaceSummary,
  getRacePredictions,
  getLapPositions,
  getPredictedLapPositions,
  getActualResults,
  getTyreIntelligence,
  getPredictedTyreIntelligence,
  getAvailableRaces,
  type PredictionRow,
  type LapPositionData,
  type ActualResult,
  type TyreIntelligenceData,
  type RaceInfo
} from "../../utils/fileReader";

const RaceTimeline = dynamic(
  () => import("../../components/RaceTimeline").then((m) => m.RaceTimeline),
  { ssr: false }
);

interface RacePageProps {
  race: RaceInfo;
  availableRaces: RaceInfo[];
  markdownReport: string | null;
  predictedMarkdownReport: string | null;
  predictions: PredictionRow[] | null;
  actualResults: ActualResult[] | null;
  lapPositions: LapPositionData | null;
  predictedLapPositions: LapPositionData | null;
  tyreData: TyreIntelligenceData | null;
  predictedTyreData: TyreIntelligenceData | null;
}

export async function getStaticPaths() {
  const races = getAvailableRaces(2026);
  const paths = races.map((r) => ({
    params: { round: r.round.toString() },
  }));

  return { paths, fallback: "blocking" };
}

export async function getStaticProps({ params }: { params: { round: string } }) {
  const year = 2026;
  const roundNum = parseInt(params.round);
  const availableRaces = getAvailableRaces(year);
  const race = availableRaces.find((r) => r.round === roundNum);

  if (!race) return { notFound: true };

  const markdownReport = getRaceSummary(year, race.dirName, roundNum);
  const predictedMarkdownReport = getPredictedRaceSummary(year, roundNum);
  const predictions = getRacePredictions(year, race.dirName) ?? [];
  const actualResults = getActualResults(year, roundNum) ?? [];
  const lapPositions = getLapPositions(year, roundNum);
  const predictedLapPositions = getPredictedLapPositions(year, roundNum);
  const tyreData = getTyreIntelligence(year, roundNum);
  const predictedTyreData = getPredictedTyreIntelligence(year, roundNum);

  return {
    props: { race, availableRaces, markdownReport, predictedMarkdownReport, predictions, actualResults, lapPositions, predictedLapPositions, tyreData, predictedTyreData },
    revalidate: 3600,
  };
}

export default function RacePage({ 
  race,
  availableRaces,
  markdownReport,
  predictedMarkdownReport,
  predictions, 
  actualResults, 
  lapPositions, 
  predictedLapPositions,
  tyreData,
  predictedTyreData
}: RacePageProps) {
  const [tableView, setTableView] = useState<"predicted" | "actual">("predicted");
  const [chartView, setChartView] = useState<"predicted" | "actual">("actual");
  const [tyreView, setTyreView] = useState<"predicted" | "actual">("actual");
  const [reportView, setReportView] = useState<"predicted" | "actual">("actual");

  const currentTableData = tableView === "predicted" ? (predictions ?? []) : (actualResults ?? []);
  const currentTyreData = tyreView === "predicted" ? (predictedTyreData ?? null) : (tyreData ?? null);
  const currentReport = reportView === "predicted" ? (predictedMarkdownReport ?? null) : (markdownReport ?? null);
  
  const winner = actualResults && actualResults.length > 0 
    ? actualResults[0] 
    : (predictions && predictions.length > 0 && predictions[0] ? { Driver: predictions[0].Driver, Team: predictions[0].Team } : null);

  const secondPlace = actualResults && actualResults.length > 1 
    ? actualResults[1] 
    : (predictions && predictions.length > 1 && predictions[1] ? { Driver: predictions[1].Driver, Team: predictions[1].Team } : null);

  return (
    <>
      <Head>
        <title>{race.name} 2026 AI Dashboard</title>
        <meta name="description" content={`AI-Powered F1 Analysis for the ${race.name}`} />
      </Head>

      <main className="min-h-screen bg-f1darker text-gray-100 pb-16 font-sans">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

          {/* ─── Header with Selector ─── */}
          <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
             <div className="flex items-center gap-3">
                <span className="text-3xl">🏁</span>
                <h1 className="text-3xl font-extrabold tracking-tight text-white">
                  F1 2026 Predictive Platform
                </h1>
             </div>
             <RaceSelector currentRound={race.round} availableRaces={availableRaces} />
          </div>

          {/* ─── Red Banner ─── */}
          <div className="mb-8 overflow-hidden rounded-xl bg-gradient-to-r from-f1red to-[#a00000] shadow-2xl">
            <div className="px-8 py-10">
              <h2 className="text-4xl font-extrabold tracking-tight text-white mb-2 drop-shadow-md">
                {race.name}
              </h2>
              <p className="text-red-100 font-medium tracking-wide">
                Season 2026 · Round {race.round} · {race.round === 4 ? '57 laps' : '70 laps'}
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
              <h2 className="text-3xl font-bold text-white mb-1">{race.round === 4 ? 'RUS' : '--'}</h2>
              <p className="text-sm text-gray-400">{race.round === 4 ? '1:27.452' : '--'}</p>
            </div>
          </div>

          {/* ─── Main Content ─── */}
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 mb-10">
            <div className="lg:col-span-7 flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-1">Race Timeline</h3>
                  <p className="text-xs text-gray-500">Coloured lines show lap-by-lap positions.</p>
                </div>
                <ViewToggle activeView={chartView} onToggle={setChartView} />
              </div>
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 p-6 shadow-inner mb-8">
                {chartView === "actual" ? (
                  lapPositions ? <RaceTimeline data={lapPositions} /> : <div className="h-64 flex items-center justify-center italic text-gray-500">No lap data.</div>
                ) : (
                  predictedLapPositions ? <RaceTimeline data={predictedLapPositions} /> : <div className="h-64 flex items-center justify-center italic text-gray-500">Simulation pending.</div>
                )}
              </div>

              <div className="mt-auto">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-1">Tyre Intelligence</h3>
                    <p className="text-xs text-gray-500">Strategy analysis. Click to highlight.</p>
                  </div>
                  <ViewToggle activeView={tyreView} onToggle={setTyreView} />
                </div>
                <div className="rounded-xl bg-f1dark border border-white/5 p-6 shadow-xl">
                  {currentTyreData ? <TyreIntelligence data={currentTyreData} /> : <p className="text-gray-500 text-sm italic">No strategy data.</p>}
                </div>
              </div>
            </div>

            <div className="lg:col-span-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold uppercase tracking-widest text-f1red">Finishing Order</h3>
                <ViewToggle activeView={tableView} onToggle={setTableView} />
              </div>
              <div className="rounded-xl bg-f1dark border border-white/5 overflow-hidden shadow-xl">
                {currentTableData.length > 0 ? <PredictionsTable data={currentTableData} view={tableView} /> : <div className="h-64 flex items-center justify-center text-gray-500">No data.</div>}
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-widest text-f1red">AI Race Analysis</h3>
              <ViewToggle activeView={reportView} onToggle={setReportView} />
            </div>
            <div className="rounded-xl bg-f1dark border border-white/5 p-6 shadow-2xl">
              {currentReport ? <RaceReport markdownContent={currentReport} /> : <p className="text-gray-500 text-sm italic">Analysis pending.</p>}
            </div>
          </div>

        </div>
      </main>
    </>
  );
}

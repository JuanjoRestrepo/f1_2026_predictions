import Head from "next/head";
import dynamic from "next/dynamic";
import { Trophy, Medal, Timer } from "lucide-react";
import { RaceReport } from "../components/RaceReport";
import { PredictionsTable } from "../components/PredictionsTable";
import {
  getRaceSummary,
  getRacePredictions,
  getLapPositions,
  type PredictionRow,
  type LapPositionData,
} from "../utils/fileReader";

// Recharts uses browser APIs — load client-side only
const RaceTimeline = dynamic(
  () => import("../components/RaceTimeline").then((m) => m.RaceTimeline),
  { ssr: false }
);

interface DashboardProps {
  markdownReport: string | null;
  predictions: PredictionRow[] | null;
  lapPositions: LapPositionData | null;
}

export async function getStaticProps() {
  const year = 2026;
  const roundNum = 4;
  const eventDirName = "Miami_Grand_Prix";

  const markdownReport = getRaceSummary(year, eventDirName, roundNum);
  const predictions = getRacePredictions(year, eventDirName) ?? [];
  const lapPositions = getLapPositions(year, roundNum);

  return {
    props: { markdownReport, predictions, lapPositions },
    revalidate: 3600,
  };
}

export default function Home({ markdownReport, predictions, lapPositions }: DashboardProps) {
  const winner = predictions && predictions.length > 0 ? predictions[0] : null;
  const secondPlace = predictions && predictions.length > 1 ? predictions[1] : null;

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
            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-yellow-500 mb-2">
                <Trophy size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Race Winner</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {winner ? winner.Driver : "--"}
              </h2>
              <p className="text-sm text-gray-400">{winner?.Team ?? ""}</p>
            </div>

            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-gray-400 mb-2">
                <Medal size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">2nd Place</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {secondPlace ? secondPlace.Driver : "--"}
              </h2>
              <p className="text-sm text-gray-400">{secondPlace?.Team ?? ""}</p>
            </div>

            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-purple-400 mb-2">
                <Timer size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Fastest Lap</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">RUS</h2>
              <p className="text-sm text-gray-400">1:27.452</p>
            </div>
          </div>

          {/* ─── Race Timeline + Finishing Order ─── */}
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 mb-10">
            {/* Race Timeline Chart (Left) */}
            <div className="lg:col-span-7 flex flex-col">
              <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-1">
                Race Timeline — Position Chart
              </h3>
              <p className="text-xs text-gray-500 mb-4">
                Coloured lines show lap-by-lap positions for the top 10 drivers. Hover to inspect.
              </p>
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 p-6">
                {lapPositions ? (
                  <RaceTimeline data={lapPositions} />
                ) : (
                  <div className="flex h-64 items-center justify-center">
                    <p className="text-gray-500 text-sm">No lap data available.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Finishing Order Table (Right) */}
            <div className="lg:col-span-5 flex flex-col">
              <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-5">
                Finishing Order
              </h3>
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 overflow-hidden">
                {predictions && predictions.length > 0 ? (
                  <PredictionsTable predictions={predictions} />
                ) : (
                  <div className="flex h-64 items-center justify-center">
                    <p className="text-gray-500 text-sm">No predictions available.</p>
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
            <div className="rounded-xl bg-f1dark border border-white/5 p-6">
              <div className="flex items-center gap-3 mb-5 border-b border-white/5 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-red-600/20 border border-red-600/30">
                  <span className="text-sm font-bold text-red-400">AI</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">Gemini 2.5 Flash</p>
                  <p className="text-xs text-gray-500">Auto-generated post-race analysis</p>
                </div>
              </div>
              {markdownReport ? (
                <RaceReport markdownContent={markdownReport} />
              ) : (
                <p className="text-gray-500 text-sm">No AI analysis available yet.</p>
              )}
            </div>
          </div>

        </div>
      </main>
    </>
  );
}

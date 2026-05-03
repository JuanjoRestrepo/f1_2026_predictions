import Head from "next/head";
import { Trophy, Medal, Timer } from "lucide-react";
import { RaceReport } from "../components/RaceReport";
import { PredictionsTable } from "../components/PredictionsTable";
import { getRaceSummary, getRacePredictions, type PredictionRow } from "../utils/fileReader";

interface DashboardProps {
  markdownReport: string | null;
  predictions: PredictionRow[] | null;
}

export async function getStaticProps() {
  const year = 2026;
  const roundNum = 4;
  const eventDirName = "Miami_Grand_Prix";

  const markdownReport = getRaceSummary(year, eventDirName, roundNum);
  const predictions = getRacePredictions(year, eventDirName) || [];

  return {
    props: {
      markdownReport,
      predictions,
    },
    revalidate: 3600,
  };
}

export default function Home({ markdownReport, predictions }: DashboardProps) {
  // Extract top drivers
  const winner = predictions && predictions.length > 0 ? predictions[0] : null;
  const secondPlace = predictions && predictions.length > 1 ? predictions[1] : null;

  return (
    <>
      <Head>
        <title>F1 2026 AI Dashboard</title>
        <meta name="description" content="AI-Powered Formula 1 Predictions & Summaries" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      
      <main className="min-h-screen bg-f1darker text-gray-100 selection:bg-f1red/30 pb-12 font-sans">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          
          {/* Top Red Banner */}
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

          {/* Metric Cards */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3 mb-10">
            {/* Winner */}
            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-yellow-500 mb-2">
                <Trophy size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Race Winner</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {winner ? "George Russell" : "--"}
              </h2>
              <p className="text-sm text-gray-400">Mercedes</p>
            </div>

            {/* 2nd Place */}
            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-gray-400 mb-2">
                <Medal size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">2nd Place</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">
                {secondPlace ? "Kimi Antonelli" : "--"}
              </h2>
              <p className="text-sm text-gray-400">Mercedes</p>
            </div>

            {/* Fastest Lap */}
            <div className="rounded-xl bg-f1dark p-6 border border-white/5 flex flex-col items-center justify-center text-center">
              <div className="flex items-center gap-2 text-purple-400 mb-2">
                <Timer size={16} />
                <span className="text-xs font-bold uppercase tracking-widest">Fastest Lap</span>
              </div>
              <h2 className="text-3xl font-bold text-white mb-1">RUS</h2>
              <p className="text-sm text-gray-400">1:27.452</p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            {/* AI Report Section (Left Column) */}
            <div className="flex flex-col">
              <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-4">
                Race Timeline & AI Analysis
              </h3>
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 p-6">
                {markdownReport ? (
                  <RaceReport markdownContent={markdownReport} />
                ) : (
                  <div className="flex h-64 items-center justify-center">
                    <p className="text-gray-500 text-sm">No AI analysis available yet.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Predictions Table (Right Column) */}
            <div className="flex flex-col">
              <h3 className="text-xs font-bold uppercase tracking-widest text-f1red mb-4">
                Finishing Order
              </h3>
              <div className="flex-1 rounded-xl bg-f1dark border border-white/5 overflow-hidden">
                {predictions && predictions.length > 0 ? (
                  <PredictionsTable predictions={predictions} />
                ) : (
                  <div className="flex h-64 items-center justify-center">
                    <p className="text-gray-500 text-sm">No predictions available yet.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          
        </div>
      </main>
    </>
  );
}

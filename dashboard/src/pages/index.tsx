import Head from "next/head";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Calendar, ChevronRight, Activity, MapPin, Clock } from "lucide-react";
import { getAvailableRaces, getFullCalendar, type RaceInfo } from "../utils/fileReader";

interface HomeProps {
  availableRaces: RaceInfo[];
  fullCalendar: RaceInfo[];
}

export async function getStaticProps() {
  const year = 2026;
  const availableRaces = getAvailableRaces(year);
  const fullCalendar = getFullCalendar(year);

  return {
    props: {
      availableRaces,
      fullCalendar,
    },
    revalidate: 3600, // revalidate every hour
  };
}

function CountdownTimer({ targetDate }: { targetDate: string }) {
  const [timeLeft, setTimeLeft] = useState({ days: 0, hours: 0, minutes: 0, seconds: 0 });

  useEffect(() => {
    const target = new Date(targetDate).getTime();

    const interval = setInterval(() => {
      const now = new Date().getTime();
      const distance = target - now;

      if (distance < 0) {
        clearInterval(interval);
        return;
      }

      setTimeLeft({
        days: Math.floor(distance / (1000 * 60 * 60 * 24)),
        hours: Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
        minutes: Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)),
        seconds: Math.floor((distance % (1000 * 60)) / 1000),
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [targetDate]);

  return (
    <div className="flex gap-4 items-center">
      <div className="flex flex-col items-center bg-f1dark p-3 rounded-lg border border-gray-800 w-20">
        <span className="text-2xl font-bold text-white">{timeLeft.days}</span>
        <span className="text-xs text-gray-500 font-mono uppercase">Days</span>
      </div>
      <div className="flex flex-col items-center bg-f1dark p-3 rounded-lg border border-gray-800 w-20">
        <span className="text-2xl font-bold text-white">{timeLeft.hours}</span>
        <span className="text-xs text-gray-500 font-mono uppercase">Hrs</span>
      </div>
      <div className="flex flex-col items-center bg-f1dark p-3 rounded-lg border border-gray-800 w-20">
        <span className="text-2xl font-bold text-white">{timeLeft.minutes}</span>
        <span className="text-xs text-gray-500 font-mono uppercase">Min</span>
      </div>
      <div className="flex flex-col items-center bg-f1dark p-3 rounded-lg border border-gray-800 w-20">
        <span className="text-2xl font-bold text-f1red">{timeLeft.seconds}</span>
        <span className="text-xs text-f1red/80 font-mono uppercase">Sec</span>
      </div>
    </div>
  );
}

export default function Home({ availableRaces, fullCalendar }: HomeProps) {
  // Find the next upcoming race dynamically: first race in the calendar whose
  // date is in the future. If none remain (end of season), fall back to null.
  const today = new Date();
  const nextRace = fullCalendar.find((r) => new Date(r.date) >= today) ?? null;
  const targetDate = nextRace?.date
    ? `${nextRace.date} 08:00:00 UTC`
    : (fullCalendar[fullCalendar.length - 1]?.date ?? "December 06, 2026 08:00:00 UTC");

  // Latest race for which we actually have processed data — this is what the
  // "View AI Intelligence Report" button links to. Using nextRace here caused a
  // 404 because upcoming rounds are never in getStaticPaths until data lands.
  const latestAvailableRace =
    availableRaces.length > 0
      ? availableRaces.reduce((prev, cur) => (cur.round > prev.round ? cur : prev))
      : null;

  return (
    <div className="min-h-screen bg-f1darker text-gray-200 selection:bg-f1red selection:text-white pb-20">
      <Head>
        <title>F1 2026 Predictive Intelligence</title>
        <meta name="description" content="AI-Powered F1 2026 Race Predictions" />
      </Head>

      {/* Navigation */}
      <nav className="border-b border-gray-800 bg-black/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-6 bg-f1red transform skew-x-[-15deg]"></div>
            <span className="font-bold text-xl tracking-tight text-white">
              F1<span className="text-gray-500">2026</span> PREDICTIONS
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-full text-xs font-mono flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              SYSTEM ONLINE
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden border-b border-gray-800">
        {/* Background gradient/pattern */}
        <div className="absolute inset-0 bg-gradient-to-br from-f1darker via-f1darker to-black z-0"></div>
        <div className="absolute top-0 right-0 w-1/2 h-full bg-gradient-to-l from-f1red/5 to-transparent z-0 opacity-50"></div>
        
        <div className="max-w-7xl mx-auto px-4 py-20 relative z-10 flex flex-col md:flex-row items-center justify-between gap-10">
          <div className="flex-1 space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-f1red/10 border border-f1red/30 rounded-full text-f1red text-xs font-mono uppercase tracking-wider">
              <Activity size={14} />
              AI Intelligence Engine
            </div>
            <h1 className="text-5xl md:text-6xl font-black text-white tracking-tight leading-tight">
              ADVANCED <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-500">RACE FORECASTS</span>
            </h1>
            <p className="text-gray-400 text-lg max-w-xl leading-relaxed">
              Powered by XGBoost, LightGBM, and Google Gemini. Analyzing telemetry, track configurations, and tyre degradation to predict the 2026 F1 season with extreme precision.
            </p>
          </div>

          {/* Race Card — countdown to next GP + link to latest analysed race */}
          <div className="flex-1 w-full max-w-md">
            <div className="bg-black/40 backdrop-blur-xl border border-gray-800 rounded-2xl p-6 shadow-2xl relative overflow-hidden group">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-f1red to-orange-500"></div>
              
              <div className="flex justify-between items-start mb-6">
                <div>
                  <h3 className="text-gray-400 font-mono text-xs uppercase tracking-widest mb-1">Next Grand Prix</h3>
                  <h2 className="text-2xl font-bold text-white">{nextRace?.name || "Season Finale"}</h2>
                  {latestAvailableRace && (
                    <p className="text-gray-500 text-xs mt-1 font-mono">
                      Latest analysis: <span className="text-f1red">{latestAvailableRace.name}</span>
                    </p>
                  )}
                </div>
                <div className="w-10 h-10 rounded-full bg-f1dark flex items-center justify-center border border-gray-800">
                  <MapPin size={18} className="text-f1red" />
                </div>
              </div>

              <div className="mb-8">
                <CountdownTimer targetDate={targetDate} />
              </div>

              {latestAvailableRace ? (
                <Link 
                  href={`/race/${latestAvailableRace.round}`}
                  className="w-full py-3 bg-f1red hover:bg-red-700 text-white font-bold rounded-lg transition-colors flex items-center justify-center gap-2 group-hover:shadow-[0_0_20px_rgba(225,6,0,0.4)]"
                >
                  View AI Intelligence Report
                  <ChevronRight size={18} />
                </Link>
              ) : (
                <div className="w-full py-3 bg-gray-800 text-gray-500 font-bold rounded-lg flex items-center justify-center gap-2 cursor-not-allowed">
                  <Clock size={18} />
                  Analysis Pending
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Stats Row */}
      <section className="border-b border-gray-800 bg-black/20">
        <div className="max-w-7xl mx-auto px-4 py-8 grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="space-y-1">
            <p className="text-gray-500 font-mono text-xs uppercase">Model Accuracy (MAE)</p>
            <p className="text-2xl font-bold text-white">0.142s</p>
          </div>
          <div className="space-y-1">
            <p className="text-gray-500 font-mono text-xs uppercase">Races Processed</p>
            <p className="text-2xl font-bold text-white">{availableRaces.length} / 22</p>
          </div>
          <div className="space-y-1">
            <p className="text-gray-500 font-mono text-xs uppercase">Data Points</p>
            <p className="text-2xl font-bold text-white">4.2M+</p>
          </div>
          <div className="space-y-1">
            <p className="text-gray-500 font-mono text-xs uppercase">Prediction Engine</p>
            <p className="text-2xl font-bold text-white">Stacking Regressor</p>
          </div>
        </div>
      </section>

      {/* Calendar Grid */}
      <section className="max-w-7xl mx-auto px-4 py-16">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-3xl font-bold text-white mb-2">2026 Season Calendar</h2>
            <p className="text-gray-400">Select a completed race to view predictive analytics and AI insights.</p>
          </div>
          <Calendar size={32} className="text-gray-600" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {fullCalendar.map((race) => {
            const isAvailable = availableRaces.some(r => r.round === race.round);
            // Mark the next race dynamically — the first future round, not a hardcoded number.
            const isNext = nextRace?.round === race.round;

            return (
              <div 
                key={race.round}
                className={`relative rounded-xl border p-5 transition-all duration-300 ${
                  isAvailable 
                    ? "bg-f1dark border-gray-700 hover:border-f1red/50 hover:bg-gray-900" 
                    : isNext
                    ? "bg-f1red/5 border-f1red/30"
                    : "bg-black/30 border-gray-800 opacity-60 grayscale"
                }`}
              >
                {isNext && (
                  <div className="absolute top-0 right-0 bg-f1red text-white text-[10px] font-bold px-2 py-1 rounded-bl-lg rounded-tr-xl uppercase tracking-wider">
                    Next Race
                  </div>
                )}
                
                <div className="flex items-start justify-between mb-4">
                  <span className="text-4xl font-black text-gray-800">
                    {race.round.toString().padStart(2, '0')}
                  </span>
                  {isAvailable && (
                    <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e]"></div>
                  )}
                </div>
                
                <h3 className={`text-lg font-bold mb-1 ${isAvailable ? "text-white" : "text-gray-400"}`}>
                  {race.name}
                </h3>
                
                <div className="flex items-center gap-2 text-sm text-gray-500 font-mono mb-6">
                  <Clock size={14} />
                  {race.date}
                </div>

                {isAvailable ? (
                  <Link 
                    href={`/race/${race.round}`}
                    className="inline-flex items-center text-sm font-bold text-f1red hover:text-red-400 transition-colors"
                  >
                    View Intelligence <ChevronRight size={16} className="ml-1" />
                  </Link>
                ) : (
                  <span className="inline-flex items-center text-sm font-medium text-gray-600">
                    Awaiting Data
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

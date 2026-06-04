import fs from "fs";
import path from "path";
import Papa from "papaparse";

export interface RaceInfo {
  round: number;
  name: string;
  year: number;
  dirName: string;
  date: string;
}

/**
 * Scans the reports directory to find all available races.
 */
export function getAvailableRaces(year: number): RaceInfo[] {
  const yearDir = path.join(getReportsDirectory(), year.toString());
  if (!fs.existsSync(yearDir)) return [];

  // In our structure, Miami is a folder, and summaries are in another folder.
  // We'll define a mapping or look for specific markers.
  // For this project, let's look at the summaries folder and extract round numbers.
  const summariesDir = path.join(yearDir, "summaries");
  if (!fs.existsSync(summariesDir)) return [];

  const files = fs.readdirSync(summariesDir);
  const rounds = new Set<number>();
  files.forEach(f => {
    const match = f.match(/round_(\d+)/);
    if (match && match[1]) rounds.add(parseInt(match[1]));
  });

  const fullCalendar = getFullCalendar(year);
  
  return Array.from(rounds).sort((a, b) => a - b).map(r => {
    const raceDef = fullCalendar.find(race => race.round === r);
    return {
      round: r,
      name: raceDef?.name || `Round ${r}`,
      year,
      dirName: raceDef?.dirName || `Round_${r}`,
      date: raceDef?.date || "TBD"
    };
  });
}

/**
 * Returns the full 21-race calendar for the 2026 F1 season.
 */
export function getFullCalendar(year: number): RaceInfo[] {
  // Using realistic 2026 round assignments based on the platform's config registry
  const roundNames: Record<number, { name: string; dir: string; date: string }> = {
    1: { name: "Bahrain Grand Prix", dir: "Bahrain_Grand_Prix", date: "March 01, 2026" },
    2: { name: "Saudi Arabian Grand Prix", dir: "Saudi_Arabian_Grand_Prix", date: "March 08, 2026" },
    3: { name: "Australian Grand Prix", dir: "Australian_Grand_Prix", date: "March 22, 2026" },
    4: { name: "Miami Grand Prix", dir: "Miami_Grand_Prix", date: "May 03, 2026" },
    5: { name: "Emilia Romagna Grand Prix", dir: "Emilia_Romagna_Grand_Prix", date: "May 24, 2026" },
    6: { name: "Monaco Grand Prix", dir: "Monaco_Grand_Prix", date: "June 07, 2026" },
    7: { name: "Canadian Grand Prix", dir: "Canadian_Grand_Prix", date: "June 21, 2026" },
    8: { name: "Spanish Grand Prix", dir: "Spanish_Grand_Prix", date: "July 05, 2026" },
    9: { name: "Austrian Grand Prix", dir: "Austrian_Grand_Prix", date: "July 12, 2026" },
    10: { name: "British Grand Prix", dir: "British_Grand_Prix", date: "July 19, 2026" },
    11: { name: "Hungarian Grand Prix", dir: "Hungarian_Grand_Prix", date: "August 02, 2026" },
    12: { name: "Belgian Grand Prix", dir: "Belgian_Grand_Prix", date: "August 30, 2026" },
    13: { name: "Dutch Grand Prix", dir: "Dutch_Grand_Prix", date: "September 06, 2026" },
    14: { name: "Italian Grand Prix", dir: "Italian_Grand_Prix", date: "September 13, 2026" },
    15: { name: "Azerbaijan Grand Prix", dir: "Azerbaijan_Grand_Prix", date: "September 27, 2026" },
    16: { name: "Singapore Grand Prix", dir: "Singapore_Grand_Prix", date: "October 04, 2026" },
    17: { name: "United States Grand Prix", dir: "United_States_Grand_Prix", date: "October 25, 2026" },
    18: { name: "Mexico City Grand Prix", dir: "Mexico_City_Grand_Prix", date: "November 01, 2026" },
    19: { name: "São Paulo Grand Prix", dir: "Sao_Paulo_Grand_Prix", date: "November 15, 2026" },
    20: { name: "Las Vegas Grand Prix", dir: "Las_Vegas_Grand_Prix", date: "November 28, 2026" },
    21: { name: "Qatar Grand Prix", dir: "Qatar_Grand_Prix", date: "December 06, 2026" },
    22: { name: "Abu Dhabi Grand Prix", dir: "Abu_Dhabi_Grand_Prix", date: "December 13, 2026" },
  };

  return Object.entries(roundNames).map(([roundStr, data]) => ({
    round: parseInt(roundStr),
    name: data.name,
    year,
    dirName: data.dir,
    date: data.date
  }));
}

/**
 * Returns the absolute path to the reports directory.
 * Works both locally and on Vercel.
 */
function getReportsDirectory() {
  // process.cwd() in Next.js is the `dashboard` folder locally,
  // but on Vercel it may be the repo root. We check both paths to
  // ensure the correct one is used regardless of the deployment context.
  const cwd = process.cwd();
  const fromDashboard = path.join(cwd, "..", "reports");
  const fromRoot = path.join(cwd, "reports");

  if (fs.existsSync(fromDashboard)) return fromDashboard;
  if (fs.existsSync(fromRoot)) return fromRoot;
  // Default fallback — same as original
  return fromDashboard;
}

export interface PredictionRow {
  // Core identity
  Season?: string;
  RoundNumber?: string;
  EventName?: string;
  Driver: string;
  Team: string;
  // XGBoost prediction (primary)
  predicted_laptime_xgb_s: string;
  // LightGBM percentile predictions (optional)
  predicted_laptime_lgb_p05_s?: string;
  predicted_laptime_lgb_p50_s?: string;
  predicted_laptime_lgb_p95_s?: string;
  // Stack/ensemble prediction (optional, preferred when present)
  predicted_laptime_stack_s?: string;
  // Computed during sort
  predicted_position?: number;
}

/**
 * Reads a Markdown file generated by the AI Summarizer.
 */
export function getRaceSummary(year: number, eventDirName: string, roundNum: number): string | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `report_round_${roundNum}.md`
    );
    
    if (!fs.existsSync(filePath)) {
      return null;
    }
    
    return fs.readFileSync(filePath, "utf8");
  } catch (error) {
    console.error("Failed to read race summary:", error);
    return null;
  }
}

/**
 * Reads the predicted race summary markdown file.
 */
export function getPredictedRaceSummary(year: number, roundNum: number): string | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `predicted_report_round_${roundNum}.md`
    );
    if (!fs.existsSync(filePath)) return null;
    return fs.readFileSync(filePath, "utf8");
  } catch (error) {
    console.error("Failed to read predicted race summary:", error);
    return null;
  }
}

export interface PredictedResultsPayload {
  fastest_lap?: { driver: string; time_s: number } | null;
  predictions: PredictionRow[];
}

/**
 * Reads the predictions CSV file.
 */
export function getRacePredictions(year: number, eventDirName: string): PredictedResultsPayload | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      eventDirName,
      "results",
      "predictions.csv"
    );
    
    if (!fs.existsSync(filePath)) {
      return null;
    }
    
    const csvFile = fs.readFileSync(filePath, "utf8");
    const parsed = Papa.parse<PredictionRow>(csvFile, {
      header: true,
      skipEmptyLines: true,
    });
    
    let rows = parsed.data;

    // Map ensemble_laptime_s to predicted_laptime_stack_s if present
    rows = rows.map(r => {
      const anyRow = r as any;
      if (anyRow.ensemble_laptime_s && !r.predicted_laptime_stack_s) {
        r.predicted_laptime_stack_s = anyRow.ensemble_laptime_s;
      }
      return r;
    });

    // Check if the CSV is per-lap (multiple rows per driver)
    const driverSet = new Set(rows.map(r => r.Driver).filter(Boolean));
    
    // Find absolute fastest lap before aggregating
    let absoluteFastestDriver = "--";
    let absoluteFastestTime = Infinity;
    rows.forEach(r => {
      if (!r.Driver) return;
      const val = parseFloat(r.predicted_laptime_stack_s || r.predicted_laptime_xgb_s);
      if (!isNaN(val) && val < absoluteFastestTime) {
        absoluteFastestTime = val;
        absoluteFastestDriver = r.Driver;
      }
    });

    let predictedFastestLap = null;
    if (absoluteFastestTime !== Infinity) {
      predictedFastestLap = { driver: absoluteFastestDriver, time_s: absoluteFastestTime };
    }

    if (rows.length > driverSet.size && driverSet.size > 0) {
      // Aggregate by driver
      const aggregatedMap = new Map<string, {
        Driver: string;
        Team: string;
        xgbSum: number;
        stackSum: number;
        count: number;
        Season?: string;
        RoundNumber?: string;
        EventName?: string;
      }>();

      rows.forEach(r => {
        if (!r.Driver) return;
        const xgbVal = parseFloat(r.predicted_laptime_xgb_s) || 0;
        const stackVal = parseFloat(r.predicted_laptime_stack_s || "") || xgbVal;
        
        if (!aggregatedMap.has(r.Driver)) {
          aggregatedMap.set(r.Driver, {
            Driver: r.Driver,
            Team: r.Team || "",
            xgbSum: xgbVal,
            stackSum: stackVal,
            count: 1,
            Season: r.Season,
            RoundNumber: r.RoundNumber,
            EventName: r.EventName
          });
        } else {
          const existing = aggregatedMap.get(r.Driver)!;
          existing.xgbSum += xgbVal;
          existing.stackSum += stackVal;
          existing.count += 1;
        }
      });

      rows = Array.from(aggregatedMap.values()).map(item => ({
        Driver: item.Driver,
        Team: item.Team,
        predicted_laptime_xgb_s: (item.xgbSum / item.count).toString(),
        predicted_laptime_stack_s: (item.stackSum / item.count).toString(),
        Season: item.Season,
        RoundNumber: item.RoundNumber,
        EventName: item.EventName
      }));
    }

    // Sort by predicted laptime ascending to get finishing order
    // Prioritize stack prediction if available, else fallback to xgb
    const sorted = rows
      .filter(r => r.Driver && (r.predicted_laptime_stack_s || r.predicted_laptime_xgb_s))
      .sort((a, b) => {
        const valA = parseFloat(a.predicted_laptime_stack_s || a.predicted_laptime_xgb_s);
        const valB = parseFloat(b.predicted_laptime_stack_s || b.predicted_laptime_xgb_s);
        return valA - valB;
      })
      .map((row, idx) => ({ ...row, predicted_position: idx + 1 }));

    return { predictions: sorted, fastest_lap: predictedFastestLap };
  } catch (error) {
    console.error("Failed to read predictions CSV:", error);
    return null;
  }
}

export interface ActualResult {
  position: number;
  driver: string;
  team: string;
  time: string;
  gap: string;
}

export interface ActualResultsPayload {
  fastest_lap?: { driver: string; time: string; time_s?: number };
  results: ActualResult[];
}

/**
 * Reads the actual race results JSON generated post-race.
 */
export function getActualResults(year: number, roundNum: number): ActualResultsPayload | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `actual_results_round_${roundNum}.json`
    );
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      // Backwards compatibility for old runs
      return { results: parsed };
    }
    return parsed as ActualResultsPayload;
  } catch (error) {
    console.error("Failed to read actual results:", error);
    return null;
  }
}
export interface DriverLapData {
  driver: string;
  team: string;
  color: string;
  positions: Record<string, number>;
}

export interface LapPositionData {
  event: string;
  year: number;
  total_laps: number;
  drivers: DriverLapData[];
}

/**
 * Reads the lap-by-lap position JSON file generated by extract_lap_positions.py
 */
export function getLapPositions(year: number, roundNum: number): LapPositionData | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `lap_positions_round_${roundNum}.json`
    );

    if (!fs.existsSync(filePath)) {
      return null;
    }

    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as LapPositionData;
  } catch (error) {
    console.error("Failed to read lap positions:", error);
    return null;
  }
}

/**
 * Reads the predicted lap-by-lap position JSON file.
 */
export function getPredictedLapPositions(year: number, roundNum: number): LapPositionData | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `predicted_lap_positions_round_${roundNum}.json`
    );

    if (!fs.existsSync(filePath)) {
      return null;
    }

    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as LapPositionData;
  } catch (error) {
    console.error("Failed to read predicted lap positions:", error);
    return null;
  }
}

export interface TyreStint {
  stint: number;
  compound: string;
  laps: number;
  color: string;
}

export interface DriverTyreData {
  driver: string;
  fullName: string;
  team: string;
  stints: TyreStint[];
}

export interface TyreIntelligenceData {
  gp: string;
  year: number;
  total_laps?: number;
  winning_strategy: string;
  avg_pit_stop: string;
  proven_strategy_insight: string;
  drivers: DriverTyreData[];
}

/**
 * Reads the tyre intelligence JSON file.
 */
export function getTyreIntelligence(year: number, roundNum: number): TyreIntelligenceData | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `tyre_intelligence_round_${roundNum}.json`
    );
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as TyreIntelligenceData;
  } catch (error) {
    console.error("Failed to read tyre intelligence:", error);
    return null;
  }
}
/**
 * Reads the predicted tyre intelligence JSON file.
 */
export function getPredictedTyreIntelligence(year: number, roundNum: number): TyreIntelligenceData | null {
  try {
    const filePath = path.join(
      getReportsDirectory(),
      year.toString(),
      "summaries",
      `predicted_tyre_intelligence_round_${roundNum}.json`
    );
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw) as TyreIntelligenceData;
  } catch (error) {
    console.error("Failed to read predicted tyre intelligence:", error);
    return null;
  }
}


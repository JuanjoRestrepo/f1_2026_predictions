import { useEffect } from "react";
import { useRouter } from "next/router";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to the latest race (Round 4 - Miami)
    // Later this can be dynamic by fetching the latest round
    router.replace("/race/4");
  }, [router]);

  return (
    <div className="min-h-screen bg-f1darker flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="h-12 w-12 border-4 border-f1red border-t-transparent rounded-full animate-spin"></div>
        <p className="text-gray-400 font-mono text-xs uppercase tracking-widest animate-pulse">
          Loading Latest Race Data...
        </p>
      </div>
    </div>
  );
}

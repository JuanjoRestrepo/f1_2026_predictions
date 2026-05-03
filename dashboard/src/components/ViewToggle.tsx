interface ViewToggleProps {
  activeView: "predicted" | "actual";
  onToggle: (view: "predicted" | "actual") => void;
}

export function ViewToggle({ activeView, onToggle }: ViewToggleProps) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 bg-black/30 p-0.5 text-xs font-semibold">
      <button
        onClick={() => onToggle("predicted")}
        className={`rounded-md px-3 py-1.5 transition-all duration-200 ${
          activeView === "predicted"
            ? "bg-f1red text-white shadow-sm"
            : "text-gray-400 hover:text-white"
        }`}
      >
        Predicted
      </button>
      <button
        onClick={() => onToggle("actual")}
        className={`rounded-md px-3 py-1.5 transition-all duration-200 ${
          activeView === "actual"
            ? "bg-f1red text-white shadow-sm"
            : "text-gray-400 hover:text-white"
        }`}
      >
        Actual
      </button>
    </div>
  );
}

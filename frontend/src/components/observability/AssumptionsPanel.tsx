import { useSessionStore } from "@/stores/sessionStore";
import { Eye } from "lucide-react";

export default function AssumptionsPanel() {
  const assumptions = useSessionStore((s) => s.assumptions);

  if (assumptions.length === 0) {
    return <p className="px-3 py-2 text-xs text-zinc-600">No assumptions logged yet.</p>;
  }

  return (
    <div className="space-y-1 px-1 py-1">
      {assumptions.map((a, i) => (
        <div key={i} className="flex gap-2 rounded p-2 bg-amber-900/10 border border-amber-800/30">
          <Eye className="h-3.5 w-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="min-w-0">
            <span className="font-mono text-[10px] text-muted-foreground">[{a.agentId}] </span>
            <span className="text-xs text-amber-300">{a.text}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

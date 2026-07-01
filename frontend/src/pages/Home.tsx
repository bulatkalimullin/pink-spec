import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, ChevronRight, Loader2 } from "lucide-react";
import { createAndStartSession } from "@/lib/api";
import { useSessionStore } from "@/stores/sessionStore";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const SPEC_LEVELS = [
  {
    id: "L1",
    name: "Brief",
    time: "2–5 min",
    desc: "Outline, problem, users, MVP scope",
    cls: "badge-L1",
  },
  {
    id: "L2",
    name: "Standard",
    time: "10–15 min",
    desc: "Core specs + 15–30 micro-tasks",
    cls: "badge-L2",
  },
  {
    id: "L3",
    name: "Full",
    time: "20–30 min",
    desc: "All artifacts + API spec + 50–100 tasks",
    cls: "badge-L3",
  },
  {
    id: "L4",
    name: "Exhaustive",
    time: "Until approved",
    desc: "Dynamic pipeline, 100+ tasks, iterative review",
    cls: "badge-L4",
  },
];

const EXAMPLE_IDEAS = [
  "SaaS task tracker for remote teams with Kanban boards and real-time updates",
  "E-commerce platform for handmade goods with seller dashboard and payment processing",
  "Real-time fraud detection pipeline using streaming transaction data and ML models",
  "Developer portfolio builder with GitHub integration and custom domain support",
];

export default function Home() {
  const navigate = useNavigate();
  const { reset, setSessionId } = useSessionStore();
  const [idea, setIdea] = useState("");
  const [specLevel, setSpecLevel] = useState("L2");
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    if (!idea.trim() || idea.trim().length < 10) {
      toast.error("Describe your idea (at least 10 characters)");
      return;
    }

    setLoading(true);
    reset();
    try {
      let rules: Record<string, unknown> = { spec_level: specLevel };
      try {
        const saved = localStorage.getItem("pink_spec_rules");
        if (saved) {
          rules = { ...JSON.parse(saved), spec_level: specLevel };
        }
      } catch {
        /* use default rules */
      }
      if (specLevel === "L4") {
        const pipeline = (rules.pipeline as Record<string, unknown>) || {};
        rules = {
          ...rules,
          pipeline: { ...pipeline, mode: "auto" },
        };
      }
      const sessionId = await createAndStartSession(idea.trim(), rules);
      setSessionId(sessionId, specLevel, idea.trim());
      navigate(`/workspace/${sessionId}`);
    } catch (e) {
      toast.error("Failed to start session", { description: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Hero */}
      <div className="flex flex-col items-center justify-center flex-1 px-4 py-12 sm:py-20">
        <div className="w-full max-w-2xl space-y-8">
          {/* Logo */}
          <div className="flex flex-col items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-primary/40 bg-primary/10">
              <Zap className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Pink Spec Agent</h1>
            <p className="text-center text-sm text-muted-foreground max-w-md">
              Turn your idea into a complete engineering specification — product, architecture, API,
              UI, and micro-tasks — powered by a multi-agent AI system.
            </p>
          </div>

          {/* Idea input */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Describe your idea
            </label>
            <textarea
              className="w-full rounded-lg border border-border bg-card px-4 py-3 text-sm text-foreground placeholder:text-zinc-600 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none transition-colors"
              rows={4}
              placeholder="e.g. A SaaS task tracker for remote teams with Kanban boards, real-time collaboration, and time tracking"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
            />
            {/* Example ideas */}
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_IDEAS.map((ex) => (
                <button
                  key={ex}
                  onClick={() => setIdea(ex)}
                  className="rounded border border-border px-2 py-1 text-[10px] sm:text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent transition-colors text-left max-w-full truncate"
                >
                  {ex.slice(0, 50)}…
                </button>
              ))}
            </div>
          </div>

          {/* Spec level selector */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Specification level
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SPEC_LEVELS.map((level) => (
                <button
                  key={level.id}
                  onClick={() => setSpecLevel(level.id)}
                  className={cn(
                    "flex flex-col items-start rounded-lg border p-3 text-left transition-all",
                    specLevel === level.id
                      ? "border-primary/60 bg-primary/10"
                      : "border-border hover:border-border/80 hover:bg-accent/30"
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={cn(
                        "rounded border px-1.5 py-0.5 text-[10px] font-bold",
                        level.cls
                      )}
                    >
                      {level.id}
                    </span>
                    <span className="text-xs font-semibold">{level.name}</span>
                  </div>
                  <span className="text-[11px] text-pink-400/80 font-mono">{level.time}</span>
                  <span className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                    {level.desc}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              onClick={handleStart}
              disabled={loading || !idea.trim()}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Zap className="h-4 w-4" />
              )}
              {loading ? "Starting…" : "Generate Specification"}
            </button>
            <button
              onClick={() => navigate("/rules")}
              className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground hover:bg-accent transition-colors"
            >
              Configure Rules
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          {/* Links */}
          <div className="flex justify-center gap-4 text-[11px] text-zinc-600">
            <button onClick={() => navigate("/settings")} className="hover:text-muted-foreground">
              Settings
            </button>
            <span>·</span>
            <a href="/docs/SPEC_AGENT.md" className="hover:text-muted-foreground">
              Documentation
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

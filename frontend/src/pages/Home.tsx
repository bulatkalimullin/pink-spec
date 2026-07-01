import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, ChevronRight, Loader2 } from "lucide-react";
import LanguageSelector from "@/components/LanguageSelector";
import { useI18n } from "@/i18n/I18nProvider";
import { createAndStartSession } from "@/lib/api";
import { loadRulesWithLanguage } from "@/lib/rulesLanguage";
import { useSessionStore } from "@/stores/sessionStore";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const SPEC_LEVEL_IDS = ["L1", "L2", "L3", "L4"] as const;
const LEVEL_CLASSES: Record<string, string> = {
  L1: "badge-L1",
  L2: "badge-L2",
  L3: "badge-L3",
  L4: "badge-L4",
};

export default function Home() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const { reset, setSessionId } = useSessionStore();
  const [idea, setIdea] = useState("");
  const [projectName, setProjectName] = useState("");
  const [specLevel, setSpecLevel] = useState("L2");
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    if (!idea.trim() || idea.trim().length < 10) {
      toast.error(t.home.ideaTooShort);
      return;
    }

    setLoading(true);
    reset();
    try {
      let rules = loadRulesWithLanguage(specLevel);
      if (specLevel === "L4") {
        const pipeline = (rules.pipeline as Record<string, unknown>) || {};
        rules = {
          ...rules,
          pipeline: { ...pipeline, mode: "auto" },
        };
      }
      const trimmedName = projectName.trim();
      if (trimmedName) {
        rules = {
          ...rules,
          project: {
            ...((rules.project as Record<string, unknown>) || {}),
            name: trimmedName,
          },
        };
      }
      const sessionId = await createAndStartSession(idea.trim(), rules);
      setSessionId(sessionId, specLevel, idea.trim());
      navigate(`/workspace/${sessionId}`);
    } catch (e) {
      toast.error(t.home.startFailed, { description: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="flex justify-end px-4 pt-4">
        <LanguageSelector compact />
      </div>

      <div className="flex flex-col items-center justify-center flex-1 px-4 py-12 sm:py-20">
        <div className="w-full max-w-2xl space-y-8">
          <div className="flex flex-col items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-primary/40 bg-primary/10">
              <Zap className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t.home.title}</h1>
            <p className="text-center text-sm text-muted-foreground max-w-md">{t.home.subtitle}</p>
          </div>

          <LanguageSelector showHint />

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {t.home.projectName}
            </label>
            <input
              type="text"
              className="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-foreground placeholder:text-zinc-600 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
              placeholder={t.home.projectPlaceholder}
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
            <p className="text-[10px] text-muted-foreground">{t.home.projectHint}</p>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {t.home.ideaLabel}
            </label>
            <textarea
              className="w-full rounded-lg border border-border bg-card px-4 py-3 text-sm text-foreground placeholder:text-zinc-600 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none transition-colors"
              rows={4}
              placeholder={t.home.ideaPlaceholder}
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              {t.home.examples.map((ex) => (
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

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {t.home.specLevel}
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SPEC_LEVEL_IDS.map((levelId) => {
                const level = t.home.levels[levelId];
                return (
                  <button
                    key={levelId}
                    onClick={() => setSpecLevel(levelId)}
                    className={cn(
                      "flex flex-col items-start rounded-lg border p-3 text-left transition-all",
                      specLevel === levelId
                        ? "border-primary/60 bg-primary/10"
                        : "border-border hover:border-border/80 hover:bg-accent/30"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-[10px] font-bold",
                          LEVEL_CLASSES[levelId]
                        )}
                      >
                        {levelId}
                      </span>
                      <span className="text-xs font-semibold">{level.name}</span>
                    </div>
                    <span className="text-[11px] text-pink-400/80 font-mono">{level.time}</span>
                    <span className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
                      {level.desc}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

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
              {loading ? t.home.starting : t.home.generate}
            </button>
            <button
              onClick={() => navigate("/rules")}
              className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground hover:bg-accent transition-colors"
            >
              {t.nav.configureRules}
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="flex justify-center gap-4 text-[11px] text-zinc-600">
            <button onClick={() => navigate("/projects")} className="hover:text-muted-foreground">
              {t.nav.projects}
            </button>
            <span>·</span>
            <button onClick={() => navigate("/settings")} className="hover:text-muted-foreground">
              {t.nav.settings}
            </button>
            <span>·</span>
            <a href="/docs/SPEC_AGENT.md" className="hover:text-muted-foreground">
              {t.nav.documentation}
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

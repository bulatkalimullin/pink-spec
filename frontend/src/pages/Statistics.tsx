import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, BarChart3, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
  getGlobalStats,
  getSessionMetricsList,
  GlobalStats,
  rebuildStats,
  SessionMetricsSummary,
} from "@/lib/api";
import StatCard from "@/components/stats/StatCard";
import SessionsTrendChart from "@/components/stats/SessionsTrendChart";
import SpecLevelBreakdown from "@/components/stats/SpecLevelBreakdown";
import AgentLeaderboard from "@/components/stats/AgentLeaderboard";
import RecentSessionsTable from "@/components/stats/RecentSessionsTable";

export default function Statistics() {
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [sessions, setSessions] = useState<SessionMetricsSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [global, list] = await Promise.all([
        getGlobalStats(),
        getSessionMetricsList({ limit: 50 }),
      ]);
      setStats(global);
      setSessions(list.sessions);
    } catch {
      toast.error("Не удалось загрузить статистику");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      const result = await rebuildStats(false);
      toast.success(result.message);
      await load();
    } catch {
      toast.error("Ошибка пересчёта статистики");
    } finally {
      setRebuilding(false);
    }
  };

  if (loading && !stats) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const totals = stats?.totals;
  const rates = stats?.rates;
  const reliability = stats?.reliability;
  const infra = stats?.infrastructure;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur-sm">
        <Link to="/" className="rounded-md p-1.5 hover:bg-accent transition-colors">
          <ArrowLeft className="h-4 w-4 text-muted-foreground" />
        </Link>
        <BarChart3 className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">Статистика за всё время</h1>
        <div className="flex-1" />
        <button
          onClick={handleRebuild}
          disabled={rebuilding}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs hover:bg-accent disabled:opacity-50"
        >
          {rebuilding ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Пересчитать
        </button>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
        {stats?.updated_at && (
          <p className="text-[11px] text-muted-foreground">
            Обновлено: {new Date(stats.updated_at).toLocaleString("ru-RU")}
          </p>
        )}

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Всего сессий" value={totals?.sessions ?? 0} />
          <StatCard
            label="Успешных"
            value={`${rates?.success_rate ?? 0}%`}
            sub={`${totals?.completed ?? 0} completed`}
          />
          <StatCard
            label="Ср. quality"
            value={(rates?.avg_quality_score ?? 0).toFixed(1)}
            sub={`eff ${(rates?.avg_efficiency_score ?? 0).toFixed(0)} · rel ${(rates?.avg_reliability_score ?? 0).toFixed(0)}`}
          />
          <StatCard
            label="Задач / артефактов"
            value={totals?.tasks ?? 0}
            sub={`${totals?.artifacts ?? 0} артефактов`}
          />
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-border bg-card/40 p-4">
            <h2 className="mb-3 text-sm font-medium">Динамика сессий</h2>
            <SessionsTrendChart
              sessionsByDay={stats?.trends.sessions_by_day ?? []}
              avgDurationByDay={stats?.trends.avg_duration_by_day ?? []}
            />
          </div>
          <div className="rounded-lg border border-border bg-card/40 p-4">
            <h2 className="mb-3 text-sm font-medium">По уровням спецификации</h2>
            <SpecLevelBreakdown bySpecLevel={stats?.by_spec_level ?? {}} />
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-border bg-card/40 p-4">
            <h2 className="mb-3 text-sm font-medium">Leaderboard агентов</h2>
            <AgentLeaderboard agents={stats?.agent_leaderboard ?? []} />
          </div>
          <div className="rounded-lg border border-border bg-card/40 p-4">
            <h2 className="mb-3 text-sm font-medium">Надёжность (all-time)</h2>
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="Ошибки" value={totals?.errors ?? 0} />
              <StatCard label="Fallbacks" value={totals?.fallbacks ?? 0} />
              <StatCard label="Circuit breaker" value={reliability?.circuit_breaker_opens ?? 0} />
              <StatCard label="Timeouts" value={reliability?.agent_timeouts ?? 0} />
              <StatCard label="Stuck events" value={reliability?.session_stuck_events ?? 0} />
              <StatCard label="Budget warnings" value={reliability?.budget_warnings ?? 0} />
            </div>
            <h3 className="mb-2 mt-4 text-xs font-medium text-muted-foreground">Инфраструктура</h3>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded border border-border/50 p-2">
                <p className="text-muted-foreground">CPU peak</p>
                <p className="font-mono font-semibold">{infra?.avg_cpu_peak ?? 0}%</p>
              </div>
              <div className="rounded border border-border/50 p-2">
                <p className="text-muted-foreground">RAM peak</p>
                <p className="font-mono font-semibold">{infra?.avg_ram_peak ?? 0}%</p>
              </div>
              <div className="rounded border border-border/50 p-2">
                <p className="text-muted-foreground">GPU mem</p>
                <p className="font-mono font-semibold">{infra?.avg_gpu_mem_peak ?? 0}%</p>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-card/40 p-4">
          <h2 className="mb-3 text-sm font-medium">Все сессии</h2>
          <RecentSessionsTable sessions={sessions} />
        </section>
      </main>
    </div>
  );
}

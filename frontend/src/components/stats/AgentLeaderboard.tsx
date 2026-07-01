interface AgentLeaderboardProps {
  agents: {
    agent_id: string;
    total_calls: number;
    avg_duration_ms: number;
    failure_rate_pct: number;
    failures: number;
  }[];
}

function formatMs(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export default function AgentLeaderboard({ agents }: AgentLeaderboardProps) {
  if (agents.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Нет данных по агентам
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="pb-2 pr-3 font-medium">Агент</th>
            <th className="pb-2 pr-3 font-medium text-right">Вызовы</th>
            <th className="pb-2 pr-3 font-medium text-right">Ср. время</th>
            <th className="pb-2 font-medium text-right">Ошибки %</th>
          </tr>
        </thead>
        <tbody>
          {agents.slice(0, 12).map((a) => (
            <tr key={a.agent_id} className="border-b border-border/50">
              <td className="py-2 pr-3 font-mono text-foreground">{a.agent_id}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{a.total_calls}</td>
              <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                {formatMs(a.avg_duration_ms)}
              </td>
              <td
                className={`py-2 text-right tabular-nums ${
                  a.failure_rate_pct > 20
                    ? "text-red-400"
                    : a.failure_rate_pct > 5
                      ? "text-amber-400"
                      : "text-emerald-400"
                }`}
              >
                {a.failure_rate_pct.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

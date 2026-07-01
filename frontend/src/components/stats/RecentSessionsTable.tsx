import { Link } from "react-router-dom";
import { SessionMetricsSummary } from "@/lib/api";
import QualityScoreBadge from "./QualityScoreBadge";
import { cn } from "@/lib/utils";

interface RecentSessionsTableProps {
  sessions: SessionMetricsSummary[];
}

const STATUS_COLORS: Record<string, string> = {
  completed: "text-emerald-400",
  completed_partial: "text-orange-400",
  degraded: "text-orange-400",
  failed: "text-red-400",
  running: "text-sky-400",
  pending: "text-zinc-400",
};

function formatDuration(sec: number): string {
  if (sec >= 3600) return `${(sec / 3600).toFixed(1)}ч`;
  if (sec >= 60) return `${Math.round(sec / 60)}м`;
  return `${Math.round(sec)}с`;
}

export default function RecentSessionsTable({ sessions }: RecentSessionsTableProps) {
  if (sessions.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Сессий пока нет — запустите первую генерацию
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="pb-2 pr-3 font-medium">Проект</th>
            <th className="pb-2 pr-3 font-medium">ID</th>
            <th className="pb-2 pr-3 font-medium">Уровень</th>
            <th className="pb-2 pr-3 font-medium">Статус</th>
            <th className="pb-2 pr-3 font-medium text-right">Quality</th>
            <th className="pb-2 pr-3 font-medium text-right">Задачи</th>
            <th className="pb-2 pr-3 font-medium text-right">Время</th>
            <th className="pb-2 font-medium">Дата</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.session_id} className="border-b border-border/50 hover:bg-accent/30">
              <td className="py-2 pr-3 text-foreground max-w-[140px] truncate">
                {s.project_name || "—"}
              </td>
              <td className="py-2 pr-3">
                <Link
                  to={`/workspace/${s.session_id}`}
                  className="font-mono text-pink-400 hover:underline"
                >
                  {s.session_id.slice(0, 8)}
                </Link>
              </td>
              <td className="py-2 pr-3 font-semibold">{s.spec_level}</td>
              <td className={cn("py-2 pr-3 capitalize", STATUS_COLORS[s.status] ?? "text-zinc-400")}>
                {s.status}
              </td>
              <td className="py-2 pr-3 text-right">
                <QualityScoreBadge score={s.quality_score} />
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{s.tasks_total}</td>
              <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                {formatDuration(s.duration_sec)}
              </td>
              <td className="py-2 text-muted-foreground">
                {s.completed_at ? new Date(s.completed_at).toLocaleDateString("ru-RU") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

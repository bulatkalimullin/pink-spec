import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FolderKanban,
  Loader2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  deleteProject,
  exportSession,
  listProjects,
  ProjectSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  completed: "text-emerald-400",
  completed_partial: "text-orange-400",
  running: "text-sky-400",
  waiting_user: "text-sky-300",
  archived: "text-zinc-500",
  failed: "text-red-400",
  pending: "text-zinc-400",
};

export default function ProjectsAdmin() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listProjects();
      setProjects(data.projects);
    } catch {
      toast.error("Не удалось загрузить проекты");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDelete = async (p: ProjectSummary) => {
    const label = p.project_name || p.output_slug || p.session_id.slice(0, 8);
    if (
      !window.confirm(
        `Удалить проект «${label}»?\n\nАртефакты на диске будут удалены. Статистика в /statistics сохранится.`
      )
    ) {
      return;
    }
    setDeleting(p.session_id);
    try {
      await deleteProject(p.session_id);
      toast.success("Проект удалён — статистика сохранена");
      setProjects((prev) => prev.filter((x) => x.session_id !== p.session_id));
    } catch (e) {
      toast.error("Не удалось удалить", { description: String(e) });
    } finally {
      setDeleting(null);
    }
  };

  const handleExport = async (sessionId: string) => {
    try {
      const blob = await exportSession(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pink-spec-${sessionId.slice(0, 8)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed");
    }
  };

  const canDelete = (status: string) =>
    !["running", "waiting_user", "starting"].includes(status);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur-sm">
        <Link to="/" className="rounded-md p-1.5 hover:bg-accent transition-colors">
          <ArrowLeft className="h-4 w-4 text-muted-foreground" />
        </Link>
        <FolderKanban className="h-4 w-4 text-primary" />
        <h1 className="text-sm font-semibold">Проекты</h1>
        <div className="flex-1" />
        <button
          onClick={() => void load()}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Обновить
        </button>
      </header>

      <main className="mx-auto max-w-5xl p-4">
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : projects.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted-foreground">
            Проектов пока нет —{" "}
            <Link to="/" className="text-primary hover:underline">
              создайте первый
            </Link>
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-card/50 text-muted-foreground">
                  <th className="p-3 font-medium">Проект</th>
                  <th className="p-3 font-medium">Папка</th>
                  <th className="p-3 font-medium">Уровень</th>
                  <th className="p-3 font-medium">Статус</th>
                  <th className="p-3 font-medium text-right">Диск</th>
                  <th className="p-3 font-medium">Создан</th>
                  <th className="p-3 font-medium text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr
                    key={p.session_id}
                    className="border-b border-border/50 hover:bg-accent/20"
                  >
                    <td className="p-3">
                      <p className="font-medium text-foreground">
                        {p.project_name || "—"}
                      </p>
                      <p className="font-mono text-[10px] text-muted-foreground">
                        {p.session_id.slice(0, 8)}
                      </p>
                    </td>
                    <td className="p-3 font-mono text-pink-400/90">{p.output_slug}</td>
                    <td className="p-3 font-semibold">{p.spec_level}</td>
                    <td
                      className={cn(
                        "p-3 capitalize",
                        STATUS_COLORS[p.status] ?? "text-zinc-400"
                      )}
                    >
                      {p.status}
                    </td>
                    <td className="p-3 text-right tabular-nums text-muted-foreground">
                      {p.disk_size_mb > 0 ? `${p.disk_size_mb} MB` : "—"}
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString("ru-RU")}
                    </td>
                    <td className="p-3">
                      <div className="flex justify-end gap-1">
                        <Link
                          to={`/workspace/${p.session_id}`}
                          className="rounded p-1.5 hover:bg-accent"
                          title="Workspace"
                        >
                          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
                        </Link>
                        <Link
                          to={`/artifacts/${p.session_id}`}
                          className="rounded p-1.5 hover:bg-accent"
                          title="Artifacts"
                        >
                          <FolderKanban className="h-3.5 w-3.5 text-muted-foreground" />
                        </Link>
                        <button
                          onClick={() => void handleExport(p.session_id)}
                          className="rounded p-1.5 hover:bg-accent"
                          title="ZIP"
                        >
                          <Download className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                        <button
                          disabled={!canDelete(p.status) || deleting === p.session_id}
                          onClick={() => void handleDelete(p)}
                          className="rounded p-1.5 hover:bg-red-900/30 disabled:opacity-40"
                          title="Удалить"
                        >
                          {deleting === p.session_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-red-400" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5 text-red-400" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

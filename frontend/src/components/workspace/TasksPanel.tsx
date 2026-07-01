import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CheckSquare, ChevronRight } from "lucide-react";
import { getSessionTasks, getTaskContent } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TaskItem {
  path: string;
  name: string;
}

interface Props {
  sessionId: string;
}

export default function TasksPanel({ sessionId }: Props) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    getSessionTasks(sessionId)
      .then((data) => setTasks(data.tasks))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const handleSelect = async (path: string) => {
    if (selectedPath === path) {
      setSelectedPath(null);
      setContent(null);
      return;
    }
    setSelectedPath(path);
    setLoadingContent(true);
    try {
      const text = await getTaskContent(sessionId, path);
      setContent(text);
    } catch {
      setContent("*Failed to load task content*");
    } finally {
      setLoadingContent(false);
    }
  };

  const grouped = tasks.reduce<Record<string, TaskItem[]>>((acc, t) => {
    const phase = t.path.split("/")[0] ?? "other";
    if (!acc[phase]) acc[phase] = [];
    acc[phase].push(t);
    return acc;
  }, {});

  if (loading) {
    return <div className="p-4 text-sm text-muted-foreground animate-pulse">Loading tasks…</div>;
  }

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
        <CheckSquare className="h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">No tasks generated yet</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {Object.entries(grouped).map(([phase, items]) => (
          <div key={phase}>
            <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {phase.replace(/-/g, " ")}
            </p>
            <div className="space-y-0.5">
              {items.map((t) => (
                <button
                  key={t.path}
                  onClick={() => void handleSelect(t.path)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-left transition-colors",
                    selectedPath === t.path
                      ? "bg-primary/20 text-primary"
                      : "text-muted-foreground hover:bg-accent"
                  )}
                >
                  <CheckSquare className="h-3 w-3 shrink-0" />
                  <span className="truncate flex-1">{t.name.replace(/\.md$/, "")}</span>
                  <ChevronRight
                    className={cn(
                      "h-3 w-3 shrink-0 transition-transform",
                      selectedPath === t.path && "rotate-90"
                    )}
                  />
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {selectedPath && (
        <div className="border-t border-border max-h-[50%] overflow-y-auto bg-card/80 p-3">
          {loadingContent ? (
            <p className="text-xs text-muted-foreground animate-pulse">Loading…</p>
          ) : (
            <div className="prose prose-invert prose-xs max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content ?? ""}</ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

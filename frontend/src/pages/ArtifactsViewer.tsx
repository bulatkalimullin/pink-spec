import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, Download, FileText } from "lucide-react";
import { getSession, getArtifact, exportSession } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface ArtifactMeta {
  type: string;
  label: string;
}

function isYamlType(type: string): boolean {
  return type === "api_spec" || type.endsWith(".yaml") || type.endsWith(".yml");
}

export default function ArtifactsViewer() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [artifacts, setArtifacts] = useState<ArtifactMeta[]>([]);
  const [activeArtifact, setActiveArtifact] = useState<string>("");
  const [contentByType, setContentByType] = useState<Record<string, string>>({});
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  const [sessionStatus, setSessionStatus] = useState<string>("");

  const loadArtifactMeta = useCallback(async () => {
    if (!sessionId) return;
    try {
      const s = await getSession(sessionId);
      setSessionStatus(s.status ?? "");
      const manifest = s.manifest;
      if (!manifest?.artifacts) {
        setArtifacts([]);
        return;
      }
      const arts: ArtifactMeta[] = Object.keys(manifest.artifacts).map((type) => ({
        type,
        label: type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      }));
      setArtifacts(arts);
      setActiveArtifact((prev) => prev || (arts.length > 0 ? arts[0].type : ""));
    } catch {
      toast.error("Failed to load artifacts");
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    setLoadingMeta(true);
    void loadArtifactMeta().finally(() => setLoadingMeta(false));
  }, [sessionId, loadArtifactMeta]);

  useEffect(() => {
    if (!sessionId || sessionStatus !== "running") return;
    const interval = window.setInterval(() => {
      void loadArtifactMeta();
    }, 8000);
    return () => window.clearInterval(interval);
  }, [sessionId, sessionStatus, loadArtifactMeta]);

  const loadContent = useCallback(
    async (type: string) => {
      if (!sessionId || contentByType[type]) return;
      setLoadingContent(true);
      setContentError(null);
      try {
        const text = await getArtifact(sessionId, type);
        setContentByType((prev) => ({ ...prev, [type]: text }));
      } catch {
        setContentError(`Failed to load ${type}`);
      } finally {
        setLoadingContent(false);
      }
    },
    [sessionId, contentByType]
  );

  useEffect(() => {
    if (activeArtifact) void loadContent(activeArtifact);
  }, [activeArtifact, loadContent]);

  const handleExport = async () => {
    if (!sessionId) return;
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

  const currentContent = activeArtifact ? contentByType[activeArtifact] : undefined;

  const renderContent = () => {
    if (loadingMeta || (loadingContent && !currentContent)) {
      return (
        <div className="flex h-full items-center justify-center">
          <p className="text-sm text-muted-foreground animate-pulse">Loading…</p>
        </div>
      );
    }
    if (contentError && !currentContent) {
      return (
        <div className="flex h-full items-center justify-center text-sm text-red-400">
          {contentError}
        </div>
      );
    }
    if (!activeArtifact || !currentContent) {
      return (
        <div className="flex h-full items-center justify-center text-sm text-zinc-600">
          {artifacts.length === 0 ? "No artifacts yet" : "Select an artifact"}
        </div>
      );
    }
    if (isYamlType(activeArtifact)) {
      return (
        <pre className="overflow-x-auto px-4 py-6 sm:px-8 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap">
          {currentContent}
        </pre>
      );
    }
    return (
      <div className="prose prose-invert prose-sm max-w-none px-4 py-6 sm:px-8">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentContent}</ReactMarkdown>
      </div>
    );
  };

  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      <div className="flex h-12 min-w-0 items-center gap-2 border-b border-border bg-card px-3 sm:gap-3 sm:px-4">
        <button
          onClick={() => navigate(-1)}
          className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="hidden sm:inline">Back</span>
        </button>
        <span className="hidden text-border sm:inline">|</span>
        <span className="truncate text-sm font-semibold">Artifacts</span>
        <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
          {sessionId?.slice(0, 8)}
        </span>
        <div className="flex-1" />
        <button
          onClick={handleExport}
          className="flex shrink-0 items-center gap-1.5 rounded border border-border px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors sm:px-3"
          title="Download ZIP"
        >
          <Download className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Download ZIP</span>
        </button>
      </div>

      {/* Mobile artifact picker */}
      {artifacts.length > 0 && (
        <div className="border-b border-border bg-card/50 p-2 md:hidden">
          <select
            value={activeArtifact}
            onChange={(e) => setActiveArtifact(e.target.value)}
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
          >
            {artifacts.map((a) => (
              <option key={a.type} value={a.type}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="hidden w-48 flex-shrink-0 border-r border-border overflow-y-auto md:block">
          <div className="p-2 space-y-0.5">
            {artifacts.map((a) => (
              <button
                key={a.type}
                onClick={() => setActiveArtifact(a.type)}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-left transition-colors",
                  activeArtifact === a.type
                    ? "bg-primary/20 text-primary font-medium"
                    : "text-muted-foreground hover:bg-accent"
                )}
              >
                <FileText className="h-3 w-3 flex-shrink-0" />
                {a.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto min-w-0">{renderContent()}</div>
      </div>
    </div>
  );
}

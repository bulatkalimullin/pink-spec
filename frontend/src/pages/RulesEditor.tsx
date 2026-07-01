import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { ArrowLeft, Check, AlertTriangle } from "lucide-react";
import { getRulesSchema } from "@/lib/api";
import { toast } from "sonner";

const DEFAULT_RULES = {
  schema_version: "1.0",
  spec_level: "L2",
  project: { name: "my-project", domain: "general", idea_summary: null },
  constraints: {
    stack: { backend: [], frontend: [], forbidden: [] },
    deployment: "local",
    budget: "low",
    timeline_weeks: 8,
  },
  nfr: {},
  output: { language: "en", format: "markdown", include_diagrams: true },
  agent_rules: [],
  ollama: {
    llm_model: "qwen2.5:7b",
    fallback_models: ["llama3.2"],
    embedding_model: "nomic-embed-text",
    embedding_fallback: "keyword",
    temperature: 0.2,
    max_tokens: 4096,
    keep_alive: "5m",
    timeout_sec: 120,
  },
  rag: {
    enabled: true,
    sources: [],
    top_k: 8,
    saturation: { max_iterations: 5, novelty_threshold: 0.15, min_chunks: 10, query_expansion: true },
  },
  context: { summarization_enabled: true, max_raw_turns: 6, compress_at_token_pct: 70 },
  monitoring: { enabled: true, interval_sec: 3, warn_cpu_pct: 90, warn_ram_pct: 85, warn_gpu_mem_pct: 90 },
  resilience: {
    agent_timeout_sec: 600,
    stuck_detection_sec: 300,
    hitl_timeout_sec: 3600,
    max_review_cycles: 10,
    circuit_breaker_failures: 3,
    circuit_breaker_cooldown_sec: 60,
    checkpoint_every_agent: true,
    auto_resume_on_reconnect: true,
  },
  pipeline: {
    mode: "auto",
    deliverables: [],
    include_tasks: null,
  },
};

export default function RulesEditor() {
  const navigate = useNavigate();
  const [value, setValue] = useState(JSON.stringify(DEFAULT_RULES, null, 2));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void getRulesSchema().catch(() => {});
    try {
      const saved = localStorage.getItem("pink_spec_rules");
      if (saved) setValue(JSON.stringify(JSON.parse(saved), null, 2));
    } catch {
      /* keep defaults */
    }
  }, []);

  const handleChange = (val: string | undefined) => {
    const text = val ?? "";
    setValue(text);
    try {
      JSON.parse(text);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleSave = () => {
    try {
      const parsed = JSON.parse(value);
      localStorage.setItem("pink_spec_rules", JSON.stringify(parsed));
      toast.success("Rules saved to local storage");
    } catch (e) {
      toast.error("Invalid JSON");
    }
  };

  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      {/* Header */}
      <div className="flex min-h-12 flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2 sm:gap-3 sm:px-4 sm:py-0 sm:h-12">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <span className="text-border">|</span>
        <span className="text-sm font-semibold">Rules Editor</span>
        <div className="flex-1" />
        {error ? (
          <span className="flex items-center gap-1.5 text-xs text-red-400 max-w-[40%] truncate sm:max-w-none">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{error.slice(0, 60)}</span>
          </span>
        ) : (
          <span className="hidden items-center gap-1.5 text-xs text-emerald-400 sm:flex">
            <Check className="h-3.5 w-3.5" />
            Valid JSON
          </span>
        )}
        <button
          onClick={handleSave}
          disabled={!!error}
          className="rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
        >
          Save Rules
        </button>
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <Editor
          height="100%"
          language="json"
          theme="vs-dark"
          value={value}
          onChange={handleChange}
          options={{
            fontSize: 12,
            fontFamily: "JetBrains Mono, monospace",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: "on",
            lineNumbers: "on",
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 3,
          }}
        />
      </div>
    </div>
  );
}

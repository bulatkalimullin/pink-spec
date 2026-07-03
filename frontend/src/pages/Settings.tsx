import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw, Save } from "lucide-react";
import LanguageSelector from "@/components/LanguageSelector";
import { useI18n } from "@/i18n/I18nProvider";
import { toast } from "sonner";

interface Field {
  key: string;
  label: string;
  type: string;
  placeholder?: string;
  envVar?: string;
  section?: string;
  options?: { value: string; label: string }[];
}

const FIELDS: Field[] = [
  { section: "Ollama", key: "ollama_base_url", label: "Base URL", type: "text", placeholder: "http://localhost:11434", envVar: "OLLAMA_BASE_URL" },
  { section: "Ollama", key: "ollama_llm_model", label: "LLM Model", type: "text", placeholder: "qwen2.5:7b", envVar: "OLLAMA_LLM_MODEL" },
  { section: "Ollama", key: "ollama_llm_fallbacks", label: "LLM Fallbacks", type: "text", placeholder: "llama3.2,mistral", envVar: "OLLAMA_LLM_FALLBACKS" },
  { section: "Ollama", key: "ollama_embedding_model", label: "Embedding Model", type: "text", placeholder: "nomic-embed-text", envVar: "OLLAMA_EMBEDDING_MODEL" },
  {
    section: "Ollama",
    key: "ollama_embedding_fallback_models",
    label: "Embedding Fallback Models",
    type: "text",
    placeholder: "embeddinggemma:latest,nomic-embed-text",
    envVar: "OLLAMA_EMBEDDING_FALLBACK_MODELS",
  },
  {
    section: "Ollama",
    key: "ollama_embedding_fallback",
    label: "Embedding Fallback",
    type: "select",
    envVar: "OLLAMA_EMBEDDING_FALLBACK",
    options: [
      { value: "keyword", label: "keyword — BM25 при сбое Ollama embeddings" },
      { value: "none", label: "none — без fallback, ошибка при старте" },
    ],
  },
  { section: "Ollama", key: "ollama_keep_alive", label: "Keep Alive", type: "text", placeholder: "5m", envVar: "OLLAMA_KEEP_ALIVE" },
  { section: "Ollama", key: "ollama_timeout_sec", label: "Timeout (sec)", type: "number", placeholder: "120", envVar: "OLLAMA_TIMEOUT_SEC" },
  { section: "Generation", key: "llm_temperature", label: "Temperature", type: "number", placeholder: "0.2", envVar: "LLM_TEMPERATURE" },
  { section: "Generation", key: "llm_max_tokens", label: "Max Tokens", type: "number", placeholder: "4096", envVar: "LLM_MAX_TOKENS" },
  { section: "Monitoring", key: "monitor_interval_sec", label: "Metrics Interval (sec)", type: "number", placeholder: "3", envVar: "MONITOR_INTERVAL_SEC" },
  { section: "Monitoring", key: "warn_cpu_pct", label: "CPU Warning %", type: "number", placeholder: "90", envVar: "WARN_CPU_PCT" },
  { section: "Monitoring", key: "warn_ram_pct", label: "RAM Warning %", type: "number", placeholder: "85", envVar: "WARN_RAM_PCT" },
  { section: "Monitoring", key: "warn_gpu_mem_pct", label: "GPU Memory Warning %", type: "number", placeholder: "90", envVar: "WARN_GPU_MEM_PCT" },
  { section: "Resilience", key: "agent_timeout_sec", label: "Agent Timeout (sec)", type: "number", placeholder: "900", envVar: "AGENT_TIMEOUT_SEC" },
  { section: "Resilience", key: "stuck_detection_sec", label: "Stuck Detection (sec)", type: "number", placeholder: "600", envVar: "STUCK_DETECTION_SEC" },
  { section: "Resilience", key: "hitl_timeout_sec", label: "HITL Timeout (sec)", type: "number", placeholder: "7200", envVar: "HITL_TIMEOUT_SEC" },
];

function configToFormValues(config: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of FIELDS) {
    const v = config[f.key];
    if (v !== undefined && v !== null) {
      out[f.key] = String(v);
    }
  }
  return out;
}

export default function Settings() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [values, setValues] = useState<Record<string, string>>(() => {
    try {
      return JSON.parse(localStorage.getItem("pink_spec_settings") ?? "{}");
    } catch {
      return {};
    }
  });
  const [loading, setLoading] = useState(true);

  const loadFromBackend = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/system/config");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const config = await res.json();
      const fromEnv = configToFormValues(config);
      setValues((prev) => ({ ...fromEnv, ...prev }));
      toast.success(t.settings.loaded);
    } catch {
      toast.error(t.settings.loadFailed);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadFromBackend();
  }, []);

  const handleSave = () => {
    localStorage.setItem("pink_spec_settings", JSON.stringify(values));
    toast.success(t.settings.saved);
  };

  const sections = [...new Set(FIELDS.map((f) => f.section ?? "General"))];

  return (
    <div className="min-h-screen bg-background">
      <div className="flex min-h-12 flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2 sm:gap-3 sm:px-4 sm:py-0 sm:h-12">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          {t.nav.back}
        </button>
        <span className="text-border">|</span>
        <span className="text-sm font-semibold">{t.settings.title}</span>
        <div className="flex-1" />
        <button
          onClick={() => void loadFromBackend()}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-border px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 sm:px-3"
          title="Reload from .env"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">{t.settings.reload}</span>
        </button>
        <button
          onClick={handleSave}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity sm:px-4"
          title={t.settings.save}
        >
          <Save className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{t.settings.save}</span>
        </button>
      </div>

      <div className="mx-auto max-w-lg py-8 px-4 space-y-8">
        <LanguageSelector showHint />

        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{t.settings.configuration}</h2>
          <p className="text-xs text-muted-foreground">{t.settings.configHint}</p>
        </div>

        {sections.map((section) => (
          <div key={section} className="space-y-4">
            <h3 className="text-sm font-medium text-foreground">{section}</h3>
            {FIELDS.filter((f) => (f.section ?? "General") === section).map((f) => (
              <div key={f.key} className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  {f.label}
                  {f.envVar && (
                    <span className="ml-2 font-mono text-[10px] text-zinc-600">{f.envVar}</span>
                  )}
                </label>
                {f.type === "select" && f.options ? (
                  <select
                    value={values[f.key] ?? f.options[0]?.value ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors font-mono"
                  >
                    {f.options.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={f.type}
                    placeholder={f.placeholder}
                    value={values[f.key] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                    className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors font-mono"
                  />
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

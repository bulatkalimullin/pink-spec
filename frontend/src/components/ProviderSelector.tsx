import { useEffect, useState } from "react";
import { Cpu, Cloud } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { getLlmProviders, type LlmProvidersResponse } from "@/lib/api";
import {
  getStoredLlmProvider,
  setStoredLlmProvider,
  syncRulesLlmProvider,
  type LlmProviderId,
} from "@/lib/llmProvider";
import { cn } from "@/lib/utils";

interface ProviderSelectorProps {
  className?: string;
  showHint?: boolean;
}

function modelId(model: string | { id: string; label?: string }): string {
  return typeof model === "string" ? model : model.id;
}

function modelLabel(model: string | { id: string; label?: string }): string {
  return typeof model === "string" ? model : (model.label ?? model.id);
}

export default function ProviderSelector({ className, showHint = false }: ProviderSelectorProps) {
  const { t } = useI18n();
  const [provider, setProvider] = useState<LlmProviderId>(getStoredLlmProvider);
  const [model, setModel] = useState("");
  const [data, setData] = useState<LlmProvidersResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await getLlmProviders();
        if (cancelled) return;
        setData(resp);
        const current = getStoredLlmProvider();
        const p = resp.providers.find((x) => x.id === current) ?? resp.providers[0];
        const initialModel =
          current === "yandexgpt"
            ? (JSON.parse(localStorage.getItem("pink_spec_rules") || "{}") as { yandexgpt?: { model?: string } })
                .yandexgpt?.model
            : (JSON.parse(localStorage.getItem("pink_spec_rules") || "{}") as { ollama?: { llm_model?: string } })
                .ollama?.llm_model;
        const fallback = p?.default_model ?? modelId(p?.models?.[0] ?? "");
        setModel(initialModel || fallback);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeProvider = data?.providers.find((p) => p.id === provider);
  const models = activeProvider?.models ?? [];
  const unavailable = activeProvider && !activeProvider.available;

  const apply = (nextProvider: LlmProviderId, nextModel: string) => {
    setProvider(nextProvider);
    setModel(nextModel);
    setStoredLlmProvider(nextProvider);
    syncRulesLlmProvider(nextProvider, nextModel);
  };

  const handleProviderChange = (next: LlmProviderId) => {
    const p = data?.providers.find((x) => x.id === next);
    const nextModel = p?.default_model ?? modelId(p?.models?.[0] ?? "");
    apply(next, nextModel);
  };

  const handleModelChange = (nextModel: string) => {
    apply(provider, nextModel);
  };

  return (
    <div className={cn("space-y-2", className)}>
      <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
        {t.llm.label}
      </label>

      <div className="flex rounded-lg border border-border bg-card p-0.5" role="group" aria-label={t.llm.label}>
        <button
          type="button"
          onClick={() => handleProviderChange("ollama")}
          className={cn(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
            provider === "ollama"
              ? "bg-primary text-white"
              : "text-muted-foreground hover:text-foreground hover:bg-accent"
          )}
        >
          <Cpu className="h-3.5 w-3.5" />
          Ollama
        </button>
        <button
          type="button"
          onClick={() => handleProviderChange("yandexgpt")}
          className={cn(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
            provider === "yandexgpt"
              ? "bg-primary text-white"
              : "text-muted-foreground hover:text-foreground hover:bg-accent"
          )}
        >
          <Cloud className="h-3.5 w-3.5" />
          YandexGPT
        </button>
      </div>

      {loading ? (
        <p className="text-[10px] text-muted-foreground">{t.llm.loading}</p>
      ) : (
        <>
          <select
            value={model}
            onChange={(e) => handleModelChange(e.target.value)}
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
            disabled={models.length === 0}
          >
            {models.map((m) => {
              const id = modelId(m);
              return (
                <option key={id} value={id}>
                  {modelLabel(m)}
                </option>
              );
            })}
          </select>
          {unavailable && (
            <p className="text-[10px] text-amber-500/90">
              {provider === "yandexgpt" ? t.llm.yandexUnavailable : t.llm.ollamaUnavailable}
            </p>
          )}
          {showHint && <p className="text-[10px] text-muted-foreground">{t.llm.hint}</p>}
        </>
      )}
    </div>
  );
}

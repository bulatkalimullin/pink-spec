import { useCallback, useEffect, useState } from "react";
import { Cpu, Cloud } from "lucide-react";
import OllamaConfigPanel from "@/components/OllamaConfigPanel";
import { useI18n } from "@/i18n/I18nProvider";
import { getLlmProviders, type LlmProvidersResponse, type OllamaProviderInfo, type OllamaRulesConfig } from "@/lib/api";
import {
  getStoredLlmProvider,
  loadStoredOllamaConfig,
  setStoredLlmProvider,
  syncRulesLlmProvider,
  syncRulesOllamaConfig,
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

function isOllamaProvider(p: LlmProvidersResponse["providers"][number]): p is OllamaProviderInfo {
  return p.id === "ollama";
}

export default function ProviderSelector({ className, showHint = false }: ProviderSelectorProps) {
  const { t } = useI18n();
  const [provider, setProvider] = useState<LlmProviderId>(getStoredLlmProvider);
  const [yandexModel, setYandexModel] = useState("yandexgpt-lite");
  const [ollamaConfig, setOllamaConfig] = useState<OllamaRulesConfig>(loadStoredOllamaConfig);
  const [data, setData] = useState<LlmProvidersResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchProviders = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await getLlmProviders();
      setData(resp);
      const ollama = resp.providers.find(isOllamaProvider);
      if (ollama?.default_config && getStoredLlmProvider() === "ollama") {
        const stored = loadStoredOllamaConfig();
        if (!localStorage.getItem("pink_spec_rules")) {
          setOllamaConfig(ollama.default_config);
          syncRulesOllamaConfig(ollama.default_config);
        } else {
          setOllamaConfig(stored);
        }
      }
      const yandexStored = JSON.parse(localStorage.getItem("pink_spec_rules") || "{}") as {
        yandexgpt?: { model?: string };
      };
      if (yandexStored.yandexgpt?.model) setYandexModel(yandexStored.yandexgpt.model);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchProviders();
  }, [fetchProviders]);

  const activeProvider = data?.providers.find((p) => p.id === provider);
  const ollamaProvider = data?.providers.find(isOllamaProvider) ?? null;
  const yandexModels = activeProvider?.id === "yandexgpt" ? activeProvider.models : [];
  const unavailable = activeProvider && !activeProvider.available;

  const applyProvider = (nextProvider: LlmProviderId, nextYandexModel?: string) => {
    setProvider(nextProvider);
    setStoredLlmProvider(nextProvider);
    if (nextProvider === "yandexgpt") {
      const model = nextYandexModel ?? yandexModel;
      setYandexModel(model);
      syncRulesLlmProvider("yandexgpt", model);
    } else {
      syncRulesOllamaConfig(ollamaConfig);
    }
  };

  const handleProviderChange = (next: LlmProviderId) => {
    if (next === "yandexgpt") {
      const p = data?.providers.find((x) => x.id === "yandexgpt");
      const nextModel = p?.default_model ?? modelId(p?.models?.[0] ?? "yandexgpt-lite");
      applyProvider("yandexgpt", nextModel);
    } else {
      applyProvider("ollama");
    }
  };

  const handleYandexModelChange = (nextModel: string) => {
    setYandexModel(nextModel);
    applyProvider("yandexgpt", nextModel);
  };

  const handleOllamaChange = (next: OllamaRulesConfig) => {
    setOllamaConfig(next);
    syncRulesOllamaConfig(next);
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
      ) : provider === "ollama" ? (
        <>
          {!data && (
            <p className="text-[10px] text-amber-500/90">{t.llm.providersLoadFailed}</p>
          )}
          <OllamaConfigPanel
            provider={ollamaProvider}
            config={ollamaConfig}
            onChange={handleOllamaChange}
            onRefresh={() => void fetchProviders()}
            loading={loading}
          />
          {unavailable && (
            <p className="text-[10px] text-amber-500/90">{t.llm.ollamaUnavailable}</p>
          )}
        </>
      ) : (
        <>
          <select
            value={yandexModel}
            onChange={(e) => handleYandexModelChange(e.target.value)}
            className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
            disabled={yandexModels.length === 0}
          >
            {yandexModels.map((m) => {
              const id = modelId(m);
              return (
                <option key={id} value={id}>
                  {modelLabel(m)}
                </option>
              );
            })}
          </select>
          {unavailable && (
            <p className="text-[10px] text-amber-500/90">{t.llm.yandexUnavailable}</p>
          )}
        </>
      )}

      {showHint && <p className="text-[10px] text-muted-foreground">{t.llm.hint}</p>}
    </div>
  );
}

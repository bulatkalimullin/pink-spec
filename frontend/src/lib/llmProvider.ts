import { defaultMaturityForLevel, readStoredMaturity } from "@/components/SpecMaturitySelector";
import { loadRulesWithLanguage } from "@/lib/rulesLanguage";
import type { OllamaRulesConfig } from "@/lib/api";

const RULES_KEY = "pink_spec_rules";
const PROVIDER_KEY = "pink_spec_llm_provider";

export type LlmProviderId = "ollama" | "yandexgpt";

export const DEFAULT_OLLAMA_CONFIG: OllamaRulesConfig = {
  llm_model: "jayeshpandit2480/gemma3-UNCENSORED:4b",
  fallback_models: ["gemma3:4b", "gemma3:1b"],
  embedding_model: "locusai/all-minilm-l6-v2:latest",
  embedding_fallback_models: ["embeddinggemma:latest"],
  embedding_fallback: "keyword",
};

export function getStoredLlmProvider(): LlmProviderId {
  try {
    const fromKey = localStorage.getItem(PROVIDER_KEY);
    if (fromKey === "ollama" || fromKey === "yandexgpt") return fromKey;

    const raw = localStorage.getItem(RULES_KEY);
    if (raw) {
      const rules = JSON.parse(raw) as { llm_provider?: string };
      if (rules.llm_provider === "ollama" || rules.llm_provider === "yandexgpt") {
        return rules.llm_provider;
      }
    }
  } catch {
    /* defaults */
  }
  return "ollama";
}

export function setStoredLlmProvider(provider: LlmProviderId): void {
  localStorage.setItem(PROVIDER_KEY, provider);
}

export function loadStoredOllamaConfig(): OllamaRulesConfig {
  try {
    const raw = localStorage.getItem(RULES_KEY);
    if (!raw) return { ...DEFAULT_OLLAMA_CONFIG };
    const rules = JSON.parse(raw) as { ollama?: Partial<OllamaRulesConfig> };
    const o = rules.ollama ?? {};
    return {
      llm_model: o.llm_model ?? DEFAULT_OLLAMA_CONFIG.llm_model,
      fallback_models: o.fallback_models ?? [...DEFAULT_OLLAMA_CONFIG.fallback_models],
      embedding_model: o.embedding_model ?? DEFAULT_OLLAMA_CONFIG.embedding_model,
      embedding_fallback_models:
        o.embedding_fallback_models ?? [...DEFAULT_OLLAMA_CONFIG.embedding_fallback_models],
      embedding_fallback: o.embedding_fallback ?? DEFAULT_OLLAMA_CONFIG.embedding_fallback,
    };
  } catch {
    return { ...DEFAULT_OLLAMA_CONFIG };
  }
}

export function syncRulesOllamaConfig(config: OllamaRulesConfig): void {
  try {
    const raw = localStorage.getItem(RULES_KEY);
    const rules = raw ? JSON.parse(raw) : {};
    rules.llm_provider = "ollama";
    rules.ollama = {
      ...(rules.ollama ?? {}),
      ...config,
      fallback_models: [...config.fallback_models],
      embedding_fallback_models: [...config.embedding_fallback_models],
    };
    localStorage.setItem(RULES_KEY, JSON.stringify(rules));
    localStorage.setItem(PROVIDER_KEY, "ollama");
  } catch {
    localStorage.setItem(
      RULES_KEY,
      JSON.stringify({ llm_provider: "ollama", ollama: config })
    );
    localStorage.setItem(PROVIDER_KEY, "ollama");
  }
}

export function syncRulesLlmProvider(
  provider: LlmProviderId,
  model?: string
): void {
  if (provider === "ollama" && model) {
    const current = loadStoredOllamaConfig();
    syncRulesOllamaConfig({ ...current, llm_model: model });
    return;
  }
  try {
    const raw = localStorage.getItem(RULES_KEY);
    const rules = raw ? JSON.parse(raw) : {};
    rules.llm_provider = provider;
    if (provider === "yandexgpt") {
      rules.yandexgpt = {
        ...(rules.yandexgpt ?? {}),
        model: model ?? rules.yandexgpt?.model ?? "yandexgpt-lite",
      };
    }
    localStorage.setItem(RULES_KEY, JSON.stringify(rules));
    localStorage.setItem(PROVIDER_KEY, provider);
  } catch {
    localStorage.setItem(
      RULES_KEY,
      JSON.stringify({
        llm_provider: provider,
        yandexgpt: { model: model ?? "yandexgpt-lite" },
        ollama: DEFAULT_OLLAMA_CONFIG,
      })
    );
    localStorage.setItem(PROVIDER_KEY, provider);
  }
}

export function loadRulesWithProvider(specLevel?: string): Record<string, unknown> {
  const rules = loadRulesWithLanguage(specLevel);
  const provider = getStoredLlmProvider();
  const level = specLevel ?? String(rules.spec_level ?? "L2");
  const stored = rules as {
    ollama?: Partial<import("@/lib/api").OllamaRulesConfig>;
    yandexgpt?: { model?: string };
    project?: { spec_maturity?: string };
  };
  const spec_maturity =
    stored.project?.spec_maturity ?? readStoredMaturity(level) ?? defaultMaturityForLevel(level);
  return {
    ...rules,
    llm_provider: provider,
    project: {
      ...((stored.project as Record<string, unknown>) ?? {}),
      spec_maturity,
    },
    ollama: provider === "ollama" ? loadStoredOllamaConfig() : stored.ollama ?? DEFAULT_OLLAMA_CONFIG,
    yandexgpt: stored.yandexgpt ?? { model: "yandexgpt-lite" },
  };
}

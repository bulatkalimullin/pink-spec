import { loadRulesWithLanguage } from "@/lib/rulesLanguage";

const RULES_KEY = "pink_spec_rules";
const PROVIDER_KEY = "pink_spec_llm_provider";

export type LlmProviderId = "ollama" | "yandexgpt";

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

export function syncRulesLlmProvider(
  provider: LlmProviderId,
  model?: string
): void {
  try {
    const raw = localStorage.getItem(RULES_KEY);
    const rules = raw ? JSON.parse(raw) : {};
    rules.llm_provider = provider;
    if (provider === "yandexgpt") {
      rules.yandexgpt = {
        ...(rules.yandexgpt ?? {}),
        model: model ?? rules.yandexgpt?.model ?? "yandexgpt-lite",
      };
    } else if (model) {
      rules.ollama = {
        ...(rules.ollama ?? {}),
        llm_model: model,
      };
    }
    localStorage.setItem(RULES_KEY, JSON.stringify(rules));
  } catch {
    localStorage.setItem(
      RULES_KEY,
      JSON.stringify({
        llm_provider: provider,
        yandexgpt: { model: model ?? "yandexgpt-lite" },
        ollama: { llm_model: model ?? "qwen2.5:7b" },
      })
    );
  }
}

export function loadRulesWithProvider(specLevel?: string): Record<string, unknown> {
  const rules = loadRulesWithLanguage(specLevel);
  const provider = getStoredLlmProvider();
  const stored = rules as {
    ollama?: { llm_model?: string };
    yandexgpt?: { model?: string };
  };
  return {
    ...rules,
    llm_provider: provider,
    ollama: stored.ollama ?? { llm_model: "qwen2.5:7b" },
    yandexgpt: stored.yandexgpt ?? { model: "yandexgpt-lite" },
  };
}

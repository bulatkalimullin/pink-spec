import type { OllamaPreset, OllamaRulesConfig } from "@/lib/api";

function normalizeModelName(name: string): string {
  const n = name.trim();
  return n.endsWith(":latest") ? n.slice(0, -":latest".length) : n;
}

export function isModelInstalled(name: string, installed: string[]): boolean {
  if (!name) return false;
  const target = normalizeModelName(name);
  return installed.some(
    (item) =>
      normalizeModelName(item) === target ||
      item === name ||
      item.startsWith(`${target}:`)
  );
}

export function collectMissingModels(
  config: OllamaRulesConfig,
  installed: string[]
): string[] {
  const seen = new Set<string>();
  const missing: string[] = [];
  const all = [
    config.llm_model,
    ...config.fallback_models,
    config.embedding_model,
    ...config.embedding_fallback_models,
  ];
  for (const raw of all) {
    const name = raw?.trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    if (!isModelInstalled(name, installed)) missing.push(name);
  }
  return missing;
}

export function collectMissingFromPreset(preset: OllamaPreset): string[] {
  return preset.missing_models ?? [];
}

export function pullCommands(models: string[]): string {
  return models.map((m) => `ollama pull ${m}`).join("\n");
}

export function toggleListItem(list: string[], item: string): string[] {
  const trimmed = item.trim();
  if (!trimmed) return list;
  return list.includes(trimmed) ? list.filter((x) => x !== trimmed) : [...list, trimmed];
}

export function uniqueOptions(...groups: string[][]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const group of groups) {
    for (const raw of group) {
      const name = raw?.trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      out.push(name);
    }
  }
  return out;
}

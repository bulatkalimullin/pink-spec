import type { Lang } from "@/i18n/types";

const RULES_KEY = "pink_spec_rules";
const UI_LANG_KEY = "pink_spec_ui_language";

export function getStoredLang(): Lang {
  try {
    const fromUi = localStorage.getItem(UI_LANG_KEY);
    if (fromUi === "en" || fromUi === "ru") return fromUi;

    const raw = localStorage.getItem(RULES_KEY);
    if (raw) {
      const rules = JSON.parse(raw) as { output?: { ui_language?: string; language?: string } };
      const lang = rules.output?.ui_language ?? rules.output?.language;
      if (lang === "en" || lang === "ru") return lang;
    }
  } catch {
    /* defaults */
  }
  return "en";
}

export function setStoredLang(lang: Lang): void {
  localStorage.setItem(UI_LANG_KEY, lang);
}

export function syncRulesLanguage(lang: Lang): void {
  try {
    const raw = localStorage.getItem(RULES_KEY);
    const rules = raw ? JSON.parse(raw) : {};
    rules.output = {
      ...(rules.output ?? {}),
      language: lang,
      ui_language: lang,
      validate_language: rules.output?.validate_language ?? true,
    };
    localStorage.setItem(RULES_KEY, JSON.stringify(rules));
  } catch {
    localStorage.setItem(
      RULES_KEY,
      JSON.stringify({
        output: { language: lang, ui_language: lang, validate_language: true },
      })
    );
  }
}

export function loadRulesWithLanguage(specLevel?: string): Record<string, unknown> {
  let rules: Record<string, unknown> = { spec_level: specLevel ?? "L2" };
  try {
    const saved = localStorage.getItem(RULES_KEY);
    if (saved) {
      rules = { ...JSON.parse(saved), ...(specLevel ? { spec_level: specLevel } : {}) };
    }
  } catch {
    /* use defaults */
  }

  const lang = getStoredLang();
  const output = {
    ...((rules.output as Record<string, unknown>) ?? {}),
    language: lang,
    ui_language: lang,
    validate_language:
      (rules.output as Record<string, unknown> | undefined)?.validate_language ?? true,
  };
  return { ...rules, output };
}

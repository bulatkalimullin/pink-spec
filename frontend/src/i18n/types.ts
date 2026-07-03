export type Lang = "en" | "ru";

export type Messages = {
  lang: {
    label: string;
    en: string;
    ru: string;
    hint: string;
  };
  nav: Record<string, string>;
  home: {
    title: string;
    subtitle: string;
    projectName: string;
    projectPlaceholder: string;
    projectHint: string;
    ideaLabel: string;
    ideaPlaceholder: string;
    specLevel: string;
    generate: string;
    starting: string;
    ideaTooShort: string;
    startFailed: string;
    levels: Record<string, { name: string; time: string; desc: string }>;
    examples: readonly string[];
  };
  settings: Record<string, string>;
  rules: Record<string, string>;
  workspace: Record<string, string>;
  maturity: {
    label: string;
    mvp: string;
    production: string;
    enterprise: string;
    hint: string;
  };
  llm: {
    label: string;
    hint: string;
    loading: string;
    providersLoadFailed: string;
    ollamaUnavailable: string;
    yandexUnavailable: string;
    presets: string;
    presetNotReady: string;
    llmModel: string;
    llmFallbacks: string;
    embeddingModel: string;
    embeddingFallbacks: string;
    finalEmbeddingFallback: string;
    missingModels: string;
    pullHint: string;
    copyPull: string;
    refreshModels: string;
    addFallback: string;
    removeFallback: string;
    noneFallback: string;
    keywordFallback: string;
  };
};

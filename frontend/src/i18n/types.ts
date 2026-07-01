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
};

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { en } from "./en";
import { ru } from "./ru";
import type { Lang, Messages } from "./types";
import { getStoredLang, setStoredLang, syncRulesLanguage } from "@/lib/rulesLanguage";

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Messages;
}

const I18nContext = createContext<I18nContextValue | null>(null);

const MESSAGES: Record<Lang, Messages> = { en, ru };

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => getStoredLang());

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    setStoredLang(next);
    syncRulesLanguage(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(
    () => ({
      lang,
      setLang,
      t: MESSAGES[lang],
    }),
    [lang, setLang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return ctx;
}

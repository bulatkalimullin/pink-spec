import { Globe } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { Lang } from "@/i18n/types";
import { cn } from "@/lib/utils";

const OPTIONS: { code: Lang; labelKey: "en" | "ru" }[] = [
  { code: "en", labelKey: "en" },
  { code: "ru", labelKey: "ru" },
];

interface LanguageSelectorProps {
  className?: string;
  compact?: boolean;
  showHint?: boolean;
}

export default function LanguageSelector({
  className,
  compact = false,
  showHint = false,
}: LanguageSelectorProps) {
  const { lang, setLang, t } = useI18n();

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center gap-2">
        {!compact && (
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            <Globe className="h-3.5 w-3.5" />
            {t.lang.label}
          </label>
        )}
        <div
          className={cn(
            "flex rounded-lg border border-border bg-card p-0.5",
            compact && "ml-auto"
          )}
          role="group"
          aria-label={t.lang.label}
        >
          {OPTIONS.map((opt) => (
            <button
              key={opt.code}
              type="button"
              onClick={() => setLang(opt.code)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                lang === opt.code
                  ? "bg-primary text-white"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              )}
            >
              {t.lang[opt.labelKey]}
            </button>
          ))}
        </div>
      </div>
      {showHint && <p className="text-[10px] text-muted-foreground">{t.lang.hint}</p>}
    </div>
  );
}

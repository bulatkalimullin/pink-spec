import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";

const MATURITY_OPTIONS = [
  { value: "mvp", labelKey: "mvp" as const },
  { value: "production", labelKey: "production" as const },
  { value: "enterprise", labelKey: "enterprise" as const },
];

function defaultMaturityForLevel(specLevel: string): string {
  return specLevel === "L3" || specLevel === "L4" ? "production" : "mvp";
}

function readStoredMaturity(specLevel: string): string {
  try {
    const raw = localStorage.getItem("pink_spec_rules");
    if (raw) {
      const rules = JSON.parse(raw) as { project?: { spec_maturity?: string } };
      if (rules.project?.spec_maturity) return rules.project.spec_maturity;
    }
  } catch {
    /* default */
  }
  return defaultMaturityForLevel(specLevel);
}

function persistMaturity(maturity: string): void {
  try {
    const raw = localStorage.getItem("pink_spec_rules");
    const rules = raw ? JSON.parse(raw) : {};
    rules.project = { ...(rules.project ?? {}), spec_maturity: maturity };
    localStorage.setItem("pink_spec_rules", JSON.stringify(rules));
  } catch {
    localStorage.setItem(
      "pink_spec_rules",
      JSON.stringify({ project: { spec_maturity: maturity } })
    );
  }
}

interface SpecMaturitySelectorProps {
  specLevel: string;
  className?: string;
}

export default function SpecMaturitySelector({ specLevel, className = "" }: SpecMaturitySelectorProps) {
  const { t } = useI18n();
  const [maturity, setMaturity] = useState(() => readStoredMaturity(specLevel));

  useEffect(() => {
    const stored = readStoredMaturity(specLevel);
    if (!localStorage.getItem("pink_spec_rules")) {
      const auto = defaultMaturityForLevel(specLevel);
      setMaturity(auto);
      persistMaturity(auto);
    } else {
      setMaturity(stored);
    }
  }, [specLevel]);

  const handleChange = (value: string) => {
    setMaturity(value);
    persistMaturity(value);
  };

  return (
    <div className={`space-y-1 ${className}`}>
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        {t.maturity.label}
      </label>
      <select
        value={maturity}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
      >
        {MATURITY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {t.maturity[opt.labelKey]}
          </option>
        ))}
      </select>
      <p className="text-[10px] text-muted-foreground">{t.maturity.hint}</p>
    </div>
  );
}

export { defaultMaturityForLevel, readStoredMaturity };

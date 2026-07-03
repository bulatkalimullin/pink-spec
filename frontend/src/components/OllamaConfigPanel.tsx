import { useMemo } from "react";
import { AlertTriangle, Copy, RefreshCw, X } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { OllamaProviderInfo, OllamaRulesConfig } from "@/lib/api";
import {
  collectMissingModels,
  pullCommands,
  toggleListItem,
  uniqueOptions,
} from "@/lib/ollamaPresets";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface OllamaConfigPanelProps {
  provider: OllamaProviderInfo | null;
  config: OllamaRulesConfig;
  onChange: (config: OllamaRulesConfig) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

function ModelSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const items = uniqueOptions([value], options);
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
      >
        {items.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}

function FallbackTags({
  label,
  selected,
  options,
  exclude,
  onChange,
}: {
  label: string;
  selected: string[];
  options: string[];
  exclude?: string;
  onChange: (next: string[]) => void;
}) {
  const { t } = useI18n();
  const available = uniqueOptions(options).filter((m) => m !== exclude && !selected.includes(m));

  return (
    <div className="space-y-1.5">
      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <div className="flex flex-wrap gap-1.5 min-h-[28px]">
        {selected.map((m) => (
          <span
            key={m}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px]"
          >
            {m}
            <button
              type="button"
              aria-label={t.llm.removeFallback}
              onClick={() => onChange(selected.filter((x) => x !== m))}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        {selected.length === 0 && (
          <span className="text-[10px] text-zinc-600 py-1">—</span>
        )}
      </div>
      {available.length > 0 && (
        <select
          defaultValue=""
          onChange={(e) => {
            if (e.target.value) {
              onChange(toggleListItem(selected, e.target.value));
              e.target.value = "";
            }
          }}
          className="w-full rounded-lg border border-dashed border-border bg-card/50 px-2 py-1.5 text-[11px] text-muted-foreground"
        >
          <option value="">{t.llm.addFallback}…</option>
          {available.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export default function OllamaConfigPanel({
  provider,
  config,
  onChange,
  onRefresh,
  loading,
}: OllamaConfigPanelProps) {
  const { t } = useI18n();

  const installed = provider?.installed_models ?? [];
  const llmOptions = uniqueOptions(installed, provider?.llm_model_hints ?? [], [config.llm_model]);
  const embedOptions = uniqueOptions(
    provider?.embedding_model_hints ?? [],
    installed,
    [config.embedding_model]
  );

  const missing = useMemo(
    () => (provider ? collectMissingModels(config, installed) : []),
    [config, installed, provider]
  );

  const applyPreset = (presetId: string) => {
    const preset = provider?.presets.find((p) => p.id === presetId);
    if (preset) onChange({ ...preset.config });
  };

  const copyPull = async () => {
    const text = pullCommands(missing);
    await navigator.clipboard.writeText(text);
    toast.success(t.llm.copyPull);
  };

  return (
    <div className="space-y-3">
      {provider?.presets && provider.presets.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {t.llm.presets}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {provider.presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                title={preset.description}
                onClick={() => applyPreset(preset.id)}
                className={cn(
                  "rounded-lg border px-2.5 py-1.5 text-left text-[11px] transition-colors",
                  "border-border bg-card hover:border-primary/40 hover:bg-accent"
                )}
              >
                <span className="font-medium text-foreground">{preset.label}</span>
                {!preset.ready && (
                  <span className="ml-1.5 text-amber-500/90">({t.llm.presetNotReady})</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      <ModelSelect
        label={t.llm.llmModel}
        value={config.llm_model}
        options={llmOptions}
        onChange={(llm_model) => onChange({ ...config, llm_model })}
      />

      <FallbackTags
        label={t.llm.llmFallbacks}
        selected={config.fallback_models}
        options={llmOptions}
        exclude={config.llm_model}
        onChange={(fallback_models) => onChange({ ...config, fallback_models })}
      />

      <ModelSelect
        label={t.llm.embeddingModel}
        value={config.embedding_model}
        options={embedOptions}
        onChange={(embedding_model) => onChange({ ...config, embedding_model })}
      />

      <FallbackTags
        label={t.llm.embeddingFallbacks}
        selected={config.embedding_fallback_models}
        options={embedOptions}
        exclude={config.embedding_model}
        onChange={(embedding_fallback_models) => onChange({ ...config, embedding_fallback_models })}
      />

      <div className="space-y-1">
        <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {t.llm.finalEmbeddingFallback}
        </label>
        <select
          value={config.embedding_fallback}
          onChange={(e) =>
            onChange({
              ...config,
              embedding_fallback: e.target.value as OllamaRulesConfig["embedding_fallback"],
            })
          }
          className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
        >
          {(provider?.embedding_fallback_options ?? [
            { value: "keyword", label: t.llm.keywordFallback },
            { value: "none", label: t.llm.noneFallback },
          ]).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {missing.length > 0 && (
        <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 p-3 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-amber-200/90">{t.llm.missingModels}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{t.llm.pullHint}</p>
              <pre className="mt-2 overflow-x-auto rounded bg-black/30 p-2 text-[10px] text-zinc-300 whitespace-pre-wrap">
                {pullCommands(missing)}
              </pre>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void copyPull()}
              className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] hover:bg-accent"
            >
              <Copy className="h-3 w-3" />
              {t.llm.copyPull}
            </button>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] hover:bg-accent disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
                {t.llm.refreshModels}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

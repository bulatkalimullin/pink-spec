import { useCallback, useEffect, useMemo, useState } from "react";
import { MessageCircleQuestion, Send } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { getSession, submitAnswersBatch } from "@/lib/api";
import { useSessionStore } from "@/stores/sessionStore";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface OpenQuestion {
  id: string;
  text: string;
  priority: string;
  options: string[];
  required?: boolean;
}

interface Props {
  sessionId: string;
  onCountChange?: (count: number) => void;
}

export default function HitlPanel({ sessionId, onCountChange }: Props) {
  const { t } = useI18n();
  const { sessionStatus, intakeSummary } = useSessionStore();
  const [questions, setQuestions] = useState<OpenQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchQuestions = useCallback(async () => {
    try {
      const s = await getSession(sessionId);
      const qs = (s.open_questions ?? []) as OpenQuestion[];
      setQuestions(qs);
      onCountChange?.(qs.length);
    } catch {
      /* ignore polling errors */
    } finally {
      setLoading(false);
    }
  }, [sessionId, onCountChange]);

  useEffect(() => {
    void fetchQuestions();
    const id = setInterval(() => void fetchQuestions(), 3000);
    return () => clearInterval(id);
  }, [fetchQuestions]);

  const allAnswered = useMemo(
    () =>
      questions.every((q) => {
        const custom = (customAnswers[q.id] ?? "").trim();
        if (custom.length > 0) return true;
        return (answers[q.id] ?? "").trim().length > 0;
      }),
    [questions, answers, customAnswers]
  );

  const resolveAnswer = (q: OpenQuestion) => {
    const custom = (customAnswers[q.id] ?? "").trim();
    if (custom.length > 0) return custom;
    return (answers[q.id] ?? "").trim();
  };

  const handleSubmitAll = async () => {
    if (!allAnswered) {
      toast.error(t.workspace.answerAll);
      return;
    }
    setSubmitting(true);
    try {
      const payload: Record<string, string> = {};
      for (const q of questions) {
        payload[q.id] = resolveAnswer(q);
      }
      const res = await submitAnswersBatch(sessionId, payload);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? "Submit failed");
      }
      toast.success(t.workspace.submitSuccess);
      setQuestions([]);
      setAnswers({});
      setCustomAnswers({});
      onCountChange?.(0);
    } catch (e) {
      toast.error(t.workspace.submitFailed, { description: String(e) });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-sm text-muted-foreground animate-pulse">{t.workspace.loading}</div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
        <MessageCircleQuestion className="h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">{t.workspace.noQuestions}</p>
      </div>
    );
  }

  const waiting = sessionStatus === "waiting_user";

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-border p-3 space-y-1">
        <p className="text-xs font-semibold text-sky-300">
          {waiting ? t.workspace.waitingTitle : t.workspace.questionsTitle}
        </p>
        <p className="text-[10px] text-muted-foreground">
          {t.workspace.questionsHint.replace("{count}", String(questions.length))}
        </p>
        {intakeSummary && (
          <p className="text-[10px] text-sky-300/80 italic">{intakeSummary}</p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 p-3">
        {questions.map((q, idx) => (
          <div key={q.id} className="rounded-lg border border-border bg-card p-3 space-y-2">
            <div className="flex items-start gap-2">
              <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] font-bold text-zinc-400">
                {idx + 1}
              </span>
              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase",
                  q.priority === "critical"
                    ? "bg-red-900/50 text-red-300"
                    : q.priority === "high"
                    ? "bg-amber-900/50 text-amber-300"
                    : "bg-zinc-800 text-zinc-400"
                )}
              >
                {q.priority}
              </span>
              <p className="text-sm text-foreground leading-snug">{q.text}</p>
            </div>

            {q.options.length >= 2 ? (
              <div className="space-y-2 pl-6">
                <div className="space-y-1">
                  {q.options.map((opt) => (
                    <label
                      key={opt}
                      className="flex items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent cursor-pointer"
                    >
                      <input
                        type="radio"
                        name={`q-${q.id}`}
                        value={opt}
                        checked={answers[q.id] === opt && !(customAnswers[q.id] ?? "").trim()}
                        onChange={() => {
                          setAnswers((prev) => ({ ...prev, [q.id]: opt }));
                          setCustomAnswers((prev) => ({ ...prev, [q.id]: "" }));
                        }}
                        className="accent-primary"
                      />
                      {opt}
                    </label>
                  ))}
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground">{t.workspace.customAnswer}</p>
                  <input
                    type="text"
                    placeholder={t.workspace.customAnswerPlaceholder}
                    value={customAnswers[q.id] ?? ""}
                    onChange={(e) => {
                      const value = e.target.value;
                      setCustomAnswers((prev) => ({ ...prev, [q.id]: value }));
                      if (value.trim()) {
                        setAnswers((prev) => ({ ...prev, [q.id]: "" }));
                      }
                    }}
                    className="w-full rounded border border-border bg-background px-3 py-2 text-xs focus:border-primary/50 focus:outline-none"
                  />
                </div>
              </div>
            ) : (
              <textarea
                rows={3}
                placeholder={t.workspace.yourAnswer}
                value={answers[q.id] ?? ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                className="w-full rounded border border-border bg-background px-3 py-2 text-xs focus:border-primary/50 focus:outline-none resize-none"
              />
            )}
          </div>
        ))}
      </div>

      <div className="shrink-0 border-t border-border p-3">
        <button
          onClick={() => void handleSubmitAll()}
          disabled={submitting || !allAnswered}
          className="flex w-full items-center justify-center gap-1.5 rounded bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-50 hover:opacity-90"
        >
          <Send className="h-3.5 w-3.5" />
          {submitting
            ? t.workspace.submitting
            : `${t.workspace.submit} (${questions.length})`}
        </button>
      </div>
    </div>
  );
}

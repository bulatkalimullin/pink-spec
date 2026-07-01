import { useCallback, useEffect, useState } from "react";
import { MessageCircleQuestion, Send } from "lucide-react";
import { getSession, submitAnswer } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface OpenQuestion {
  id: string;
  text: string;
  priority: string;
  options: string[];
}

interface Props {
  sessionId: string;
  onCountChange?: (count: number) => void;
}

export default function HitlPanel({ sessionId, onCountChange }: Props) {
  const [questions, setQuestions] = useState<OpenQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<string | null>(null);
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
    const id = setInterval(() => void fetchQuestions(), 5000);
    return () => clearInterval(id);
  }, [fetchQuestions]);

  const handleSubmit = async (questionId: string) => {
    const answer = answers[questionId]?.trim();
    if (!answer) {
      toast.error("Please provide an answer");
      return;
    }
    setSubmitting(questionId);
    try {
      const res = await submitAnswer(sessionId, questionId, answer);
      if (!res.ok) throw new Error("Submit failed");
      toast.success("Answer submitted");
      setQuestions((prev) => {
        const next = prev.filter((q) => q.id !== questionId);
        onCountChange?.(next.length);
        return next;
      });
      setAnswers((prev) => {
        const next = { ...prev };
        delete next[questionId];
        return next;
      });
    } catch {
      toast.error("Failed to submit answer");
    } finally {
      setSubmitting(null);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-sm text-muted-foreground animate-pulse">Loading questions…</div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
        <MessageCircleQuestion className="h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">No open questions</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-3">
      {questions.map((q) => (
        <div key={q.id} className="rounded-lg border border-border bg-card p-3 space-y-2">
          <div className="flex items-start gap-2">
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

          {q.options.length > 0 ? (
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
                    checked={answers[q.id] === opt}
                    onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                    className="accent-primary"
                  />
                  {opt}
                </label>
              ))}
            </div>
          ) : (
            <textarea
              rows={3}
              placeholder="Your answer…"
              value={answers[q.id] ?? ""}
              onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
              className="w-full rounded border border-border bg-background px-3 py-2 text-xs focus:border-primary/50 focus:outline-none resize-none"
            />
          )}

          <button
            onClick={() => void handleSubmit(q.id)}
            disabled={submitting === q.id || !answers[q.id]?.trim()}
            className="flex w-full items-center justify-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50 hover:opacity-90"
          >
            <Send className="h-3 w-3" />
            {submitting === q.id ? "Sending…" : "Submit Answer"}
          </button>
        </div>
      ))}
    </div>
  );
}

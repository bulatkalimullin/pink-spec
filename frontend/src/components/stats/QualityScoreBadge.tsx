import { cn } from "@/lib/utils";

interface QualityScoreBadgeProps {
  score: number;
  className?: string;
}

export default function QualityScoreBadge({ score, className }: QualityScoreBadgeProps) {
  const color =
    score >= 80
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
      : score >= 60
        ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
        : score >= 40
          ? "bg-orange-500/20 text-orange-300 border-orange-500/30"
          : "bg-red-500/20 text-red-300 border-red-500/30";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-mono font-semibold",
        color,
        className
      )}
    >
      {score.toFixed(0)}
    </span>
  );
}

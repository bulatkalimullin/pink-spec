import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  className?: string;
}

export default function StatCard({ label, value, sub, className }: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card/60 p-4 backdrop-blur-sm",
        className
      )}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

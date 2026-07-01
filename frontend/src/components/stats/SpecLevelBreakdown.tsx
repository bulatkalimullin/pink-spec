import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface SpecLevelBreakdownProps {
  bySpecLevel: Record<
    string,
    { count: number; completed: number; avg_duration_sec: number; avg_tasks: number; avg_quality: number }
  >;
}

const COLORS: Record<string, string> = {
  L1: "#38bdf8",
  L2: "#34d399",
  L3: "#a78bfa",
  L4: "#f472b6",
};

export default function SpecLevelBreakdown({ bySpecLevel }: SpecLevelBreakdownProps) {
  const data = ["L1", "L2", "L3", "L4"].map((level) => ({
    level,
    count: bySpecLevel[level]?.count ?? 0,
    quality: bySpecLevel[level]?.avg_quality ?? 0,
  }));

  const hasData = data.some((d) => d.count > 0);
  if (!hasData) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        Нет сессий по уровням
      </div>
    );
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="level" tick={{ fontSize: 11, fill: "#a1a1aa" }} />
          <YAxis tick={{ fontSize: 10, fill: "#71717a" }} width={28} />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", fontSize: 11 }}
          />
          <Bar dataKey="count" name="Сессий" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.level} fill={COLORS[entry.level]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

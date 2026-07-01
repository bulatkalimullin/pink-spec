import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface SessionsTrendChartProps {
  sessionsByDay: { date: string; count: number }[];
  avgDurationByDay: { date: string; avg_duration_sec: number }[];
}

export default function SessionsTrendChart({
  sessionsByDay,
  avgDurationByDay,
}: SessionsTrendChartProps) {
  const merged = sessionsByDay.map((d) => {
    const dur = avgDurationByDay.find((x) => x.date === d.date);
    return {
      date: d.date.slice(5),
      sessions: d.count,
      avgMin: dur ? Math.round(dur.avg_duration_sec / 60) : 0,
    };
  });

  if (merged.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        Нет данных за последние 90 дней
      </div>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={merged} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#71717a" }} />
          <YAxis yAxisId="left" tick={{ fontSize: 10, fill: "#71717a" }} width={28} />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 10, fill: "#71717a" }}
            width={32}
          />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", fontSize: 11 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar yAxisId="left" dataKey="sessions" fill="#ec4899" name="Сессии" radius={[2, 2, 0, 0]} />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="avgMin"
            stroke="#a78bfa"
            strokeWidth={2}
            dot={false}
            name="Ср. длит. (мин)"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

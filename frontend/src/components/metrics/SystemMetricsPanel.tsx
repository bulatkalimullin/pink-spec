import { useSessionStore, SystemMetrics } from "@/stores/sessionStore";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";
import { AreaChart, Area, ResponsiveContainer, Tooltip } from "recharts";
import { Cpu, HardDrive, MemoryStick, CircuitBoard } from "lucide-react";

interface MetricBarProps {
  label: string;
  value: number;
  unit?: string;
  warn?: number;
  icon?: React.ReactNode;
}

function MetricBar({ label, value, unit = "%", warn = 85, icon }: MetricBarProps) {
  const isWarn = value >= warn;
  const isCritical = value >= 95;
  return (
    <div className="flex items-center gap-2">
      <div className="text-muted-foreground">{icon}</div>
      <span className="text-[11px] text-muted-foreground w-10 flex-shrink-0">{label}</span>
      <div className="flex-1 rounded-full bg-zinc-800 h-1.5 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            isCritical ? "bg-red-500" : isWarn ? "bg-amber-400" : "bg-pink-500"
          )}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span
        className={cn(
          "text-[11px] font-mono w-10 text-right flex-shrink-0",
          isCritical ? "text-red-400" : isWarn ? "text-amber-400" : "text-foreground"
        )}
      >
        {value.toFixed(0)}{unit}
      </span>
    </div>
  );
}

interface SparklineProps {
  data: { value: number }[];
  color: string;
}

function Sparkline({ data, color }: SparklineProps) {
  if (data.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={28}>
      <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.15}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Tooltip
          contentStyle={{ background: "#18181b", border: "none", fontSize: 10 }}
          formatter={(v: number) => [`${v.toFixed(0)}%`, ""]}
          labelFormatter={() => ""}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default function SystemMetricsPanel() {
  const metricsHistory = useSessionStore((s) => s.metricsHistory);
  const latest: SystemMetrics | undefined = metricsHistory[metricsHistory.length - 1];

  if (!latest) {
    return (
      <div className="px-3 py-2 text-xs text-zinc-600">Метрики пока недоступны…</div>
    );
  }

  const cpuHistory = metricsHistory.map((m) => ({ value: m.cpu_percent }));
  const ramHistory = metricsHistory.map((m) => ({ value: m.ram_percent }));
  const gpuMemPct =
    latest.gpu && latest.gpu.mem_total_mb > 0
      ? (latest.gpu.mem_used_mb / latest.gpu.mem_total_mb) * 100
      : 0;

  return (
    <div className="min-w-0 space-y-2 px-3 py-2">
      <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">System</p>

      <MetricBar
        label="CPU"
        value={latest.cpu_percent}
        warn={90}
        icon={<Cpu className="h-3 w-3" />}
      />
      <Sparkline data={cpuHistory} color="#e879a0" />

      <MetricBar
        label="RAM"
        value={latest.ram_percent}
        warn={85}
        icon={<MemoryStick className="h-3 w-3" />}
      />
      <Sparkline data={ramHistory} color="#7c3aed" />

      <MetricBar
        label="Disk"
        value={latest.disk_percent}
        warn={90}
        icon={<HardDrive className="h-3 w-3" />}
      />

      {latest.gpu ? (
        <div className="space-y-1.5 pt-0.5">
          <p
            className="text-[10px] font-medium text-muted-foreground truncate"
            title={latest.gpu.name}
          >
            {latest.gpu.name}
          </p>
          <MetricBar
            label="Load"
            value={latest.gpu.util_percent}
            warn={90}
            icon={<CircuitBoard className="h-3 w-3" />}
          />
          <MetricBar
            label="VRAM"
            value={gpuMemPct}
            warn={90}
            icon={<CircuitBoard className="h-3 w-3" />}
          />
          <div className="text-[10px] text-zinc-600 pl-6 break-words">
            {formatBytes(latest.gpu.mem_used_mb)} / {formatBytes(latest.gpu.mem_total_mb)}
            {" · "}
            {latest.gpu.temp_c}°C
            {latest.gpu.driver_version && (
              <span className="block text-zinc-700 truncate" title={latest.gpu.driver_version}>
                Driver {latest.gpu.driver_version}
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-[10px] text-zinc-600 pl-1">
          GPU недоступен — проверь nvidia runtime в backend
        </p>
      )}

      <div className="text-[10px] text-zinc-600 pt-0.5">
        Process: {latest.process_rss_mb.toFixed(0)} MB RSS
        {" "}| RAM: {formatBytes(latest.ram_used_mb)} / {formatBytes(latest.ram_total_mb)}
      </div>
    </div>
  );
}

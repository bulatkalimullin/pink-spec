import { type ClassValue, clsx } from "clsx";
import { formatDistance } from "date-fns";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export function formatDurationRu(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} сек`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m} мин ${s} сек` : `${m} мин`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h} ч ${m} мин` : `${h} ч`;
}

export function formatEtaRu(seconds: number | null | undefined): string {
  if (seconds == null) return "Оцениваем время…";
  if (seconds <= 0) return "Завершаем…";
  if (seconds < 60) return `≈ ${Math.round(seconds)} сек осталось`;
  if (seconds < 3600) {
    const m = Math.max(1, Math.round(seconds / 60));
    return `≈ ${m} мин осталось`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m > 0 ? `≈ ${h} ч ${m} мин осталось` : `≈ ${h} ч осталось`;
}

export function formatBytes(mb: number): string {
  if (mb < 1024) return `${mb.toFixed(0)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

export function formatTimeAgo(ts?: string): string {
  if (!ts) return "";
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return "";
  return formatDistance(date, new Date(), { addSuffix: true });
}

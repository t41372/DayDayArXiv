import { clsx, type ClassValue } from "clsx"
import { format } from "date-fns"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/
const UTC_TIMESTAMP_RE = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\\s*UTC$/

export function parseLocalDate(dateStr: string): Date {
  const trimmed = dateStr.trim()
  const match = DATE_RE.exec(trimmed)
  if (!match) {
    return new Date(trimmed)
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  return new Date(Date.UTC(year, month - 1, day, 23, 59, 59))
}

export function formatUtcDateFromLocal(date: Date): string {
  const localMidnight = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const year = localMidnight.getUTCFullYear()
  const month = String(localMidnight.getUTCMonth() + 1).padStart(2, "0")
  const day = String(localMidnight.getUTCDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function parseUtcTimestamp(value: string): Date | null {
  const trimmed = value.trim()
  const match = UTC_TIMESTAMP_RE.exec(trimmed)
  if (!match) {
    const fallback = new Date(trimmed)
    return Number.isNaN(fallback.getTime()) ? null : fallback
  }
  return new Date(`${match[1]}T${match[2]}Z`)
}

export function formatLocalTimestamp(value: string, fmt: string = "yyyy-MM-dd HH:mm"): string {
  const parsed = parseUtcTimestamp(value)
  if (!parsed) {
    return value
  }
  return format(parsed, fmt)
}

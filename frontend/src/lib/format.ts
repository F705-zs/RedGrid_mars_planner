// Display formatting. Missing values (null/undefined) are never shown as 0 or as safe.

export const UNAVAILABLE = "Data unavailable";
export const NOT_CHECKED = "Not checked";

type Num = number | null | undefined;
const missing = (v: Num): v is null | undefined => v === null || v === undefined || Number.isNaN(v);

export function fmtNumber(v: Num, digits = 0, unit = ""): string {
  if (missing(v)) return UNAVAILABLE;
  const s = v.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return unit ? `${s} ${unit}` : s;
}

/** Metres → "380 m" or "1.24 km". */
export function fmtDistance(m: Num): string {
  if (missing(m)) return UNAVAILABLE;
  return Math.abs(m) < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(2)} km`;
}

export function fmtKm(m: Num, digits = 2): string {
  return missing(m) ? UNAVAILABLE : `${(m / 1000).toFixed(digits)} km`;
}

/** Minutes → "3 h 05 min" / "45 min". */
export function fmtDuration(min: Num): string {
  if (missing(min)) return UNAVAILABLE;
  const total = Math.round(min);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

export const fmtDeg = (v: Num, digits = 1) => fmtNumber(v, digits, "°");
export const fmtSlope = (v: Num) => (missing(v) ? UNAVAILABLE : `${v.toFixed(1)}°`);
export const fmtText = (v: string | null | undefined) =>
  v === null || v === undefined || v.trim() === "" ? UNAVAILABLE : v;

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return UNAVAILABLE;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? UNAVAILABLE
    : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

/** Energy multiplier relative to flat regolith (RedGrid terrainDifficulty), e.g. "1.07× flat ground". */
export const fmtMultiplier = (v: Num) =>
  missing(v) ? UNAVAILABLE : `${v.toFixed(2)}× flat ground`;
/** A 0–1 share as a percentage. */
export const fmtShare = (v: Num) => (missing(v) ? UNAVAILABLE : `${Math.round(v * 100)}%`);
export const fmtKg = (v: Num, digits = 3) => fmtNumber(v, digits, "kg");
export const fmtWh = (v: Num) => fmtNumber(v, 0, "Wh");

export const titleCase = (s: string) =>
  s
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

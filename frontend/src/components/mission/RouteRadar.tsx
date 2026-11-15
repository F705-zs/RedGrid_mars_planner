import { useEffect, useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { ROUTE_TYPE_CODE, ROUTE_TYPE_LABEL } from "@/lib/labels";
import { buildRadar, DEFAULT_RADAR_KEYS, RADAR_METRICS } from "@/lib/radar";
import { cn } from "@/lib/utils";
import type { Route, RouteType } from "@/types";

const ROUTE_VAR: Record<RouteType, string> = {
  SAFEST: "--route-safest",
  SHORTEST: "--route-shortest",
  SCIENCE_FOCUSED: "--route-science",
  MISSION_PRIORITY: "--route-mission",
};

/** SVG attributes cannot read CSS variables, so the map's route colours are resolved once in the browser. */
function useRouteColours() {
  const [c, setC] = useState<Record<RouteType, string>>({
    SAFEST: "#7cc4e8",
    SHORTEST: "#e8d36a",
    SCIENCE_FOCUSED: "#7bd88f",
    MISSION_PRIORITY: "#e07a52",
  });
  useEffect(() => {
    const css = getComputedStyle(document.documentElement);
    setC((prev) => {
      const next = { ...prev };
      (Object.keys(ROUTE_VAR) as RouteType[]).forEach((t) => {
        const v = css.getPropertyValue(ROUTE_VAR[t]).trim();
        if (v) next[t] = v;
      });
      return next;
    });
  }, []);
  return c;
}

/**
 * Multidimensional comparison of the four calculated routes. Display-only: each axis is scaled from 0 to the largest
 * value among the plotted routes; tooltips and the table show the original values and units.
 */
export function RouteRadar({
  routes,
  hovered,
  onHover,
}: {
  routes: Route[];
  hovered: number | null;
  onHover: (id: number | null) => void;
}) {
  const [keys, setKeys] = useState<string[]>(DEFAULT_RADAR_KEYS);
  const colours = useRouteColours();
  const { rows, plotted, notPlotted, skipped, enough } = useMemo(
    () => buildRadar(routes, keys),
    [routes, keys],
  );

  const data = rows.map((row) => {
    const d: Record<string, number | string> = {
      axis: `${row.metric.label} ${row.metric.better === "lower" ? "↓" : "↑"}`,
      key: row.metric.key,
    };
    plotted.forEach((r) => (d[`r${r.id}`] = row.scaled[r.id]!));
    return d;
  });

  const toggle = (k: string) =>
    setKeys((ks) =>
      ks.includes(k)
        ? ks.length > 3
          ? ks.filter((x) => x !== k)
          : ks
        : ks.length < 8
          ? [...ks, k]
          : ks,
    );

  return (
    <section className="panel p-4" aria-labelledby="route-analysis-title">
      <h3 id="route-analysis-title" className="text-sm font-semibold">
        Route analysis
      </h3>
      <p className="mt-0.5 text-xs text-muted-foreground">
        ↓ lower is better · ↑ higher is better. Each axis runs from 0 to the largest value among the
        routes, so a larger shape is not automatically a better or safer route.
      </p>

      {!enough ? (
        <p className="mt-3 rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          {plotted.length === 0
            ? "No route could be calculated, so there is nothing to compare."
            : "Not enough comparable values to draw the chart (choose at least three available metrics)."}
        </p>
      ) : (
        <div
          className="mt-2 h-72"
          role="img"
          aria-label="Radar chart comparing the routes; the same values are in the table below"
        >
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="70%">
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis
                dataKey="axis"
                tick={{ fill: "currentColor", fontSize: 10 }}
                className="text-muted-foreground"
              />
              <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
              {plotted.map((r) => (
                <Radar
                  key={r.id}
                  name={`${ROUTE_TYPE_CODE[r.routeType]} · ${ROUTE_TYPE_LABEL[r.routeType]}`}
                  dataKey={`r${r.id}`}
                  stroke={colours[r.routeType]}
                  fill={colours[r.routeType]}
                  fillOpacity={hovered === r.id ? 0.25 : 0.06}
                  strokeWidth={hovered === null || hovered === r.id ? 2 : 1}
                  strokeOpacity={hovered === null || hovered === r.id ? 1 : 0.35}
                  strokeDasharray={r.feasible ? undefined : "5 4"}
                  isAnimationActive={false}
                  onMouseEnter={() => onHover(r.id)}
                  onMouseLeave={() => onHover(null)}
                />
              ))}
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const key = (payload[0]!.payload as { key: string }).key;
                  const row = rows.find((x) => x.metric.key === key)!;
                  return (
                    <div className="rounded-md border border-border bg-panel px-2.5 py-2 text-xs shadow">
                      <p className="font-medium">
                        {row.metric.label} ({row.metric.better} is better)
                      </p>
                      {plotted.map((r) => (
                        <p key={r.id} className="data-value">
                          {ROUTE_TYPE_CODE[r.routeType]} {ROUTE_TYPE_LABEL[r.routeType]}:{" "}
                          {row.metric.format(row.metric.get(r)!)}
                        </p>
                      ))}
                      {row.allZero && (
                        <p className="text-muted-foreground">All routes are 0 on this axis.</p>
                      )}
                    </div>
                  );
                }}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Legend: letter code + name, not colour alone; dashed = not feasible */}
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {plotted.map((r) => (
          <li
            key={r.id}
            className="flex items-center gap-1.5"
            onMouseEnter={() => onHover(r.id)}
            onMouseLeave={() => onHover(null)}
          >
            <span
              className="inline-block h-0.5 w-4"
              style={{
                background: colours[r.routeType],
                borderTop: r.feasible ? undefined : "2px dashed",
              }}
            />
            {ROUTE_TYPE_CODE[r.routeType]} {ROUTE_TYPE_LABEL[r.routeType]}
            {!r.feasible && <span className="text-muted-foreground">(not feasible)</span>}
          </li>
        ))}
        {notPlotted.map((r) => (
          <li key={r.id} className="text-muted-foreground">
            {ROUTE_TYPE_CODE[r.routeType]} {ROUTE_TYPE_LABEL[r.routeType]}: no route found, not
            plotted
          </li>
        ))}
      </ul>

      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          Metrics and values
        </summary>
        <div
          className="mt-2 flex flex-wrap gap-1"
          role="group"
          aria-label="Choose chart metrics (3 to 8)"
        >
          {RADAR_METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              aria-pressed={keys.includes(m.key)}
              onClick={() => toggle(m.key)}
              className={cn(
                "rounded border px-1.5 py-0.5",
                keys.includes(m.key)
                  ? "border-sand bg-sand/15 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
        {skipped.length > 0 && (
          <p className="mt-1.5 text-muted-foreground">
            Left out: {skipped.map((s) => `${s.metric.label} (${s.reason})`).join("; ")}.
          </p>
        )}
        <div className="mt-2 overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Original route values behind the radar chart</caption>
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-2 font-medium">Metric</th>
                {routes.map((r) => (
                  <th key={r.id} className="py-1 pr-2 font-medium">
                    {ROUTE_TYPE_CODE[r.routeType]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="data-value">
              {RADAR_METRICS.filter((m) => keys.includes(m.key)).map((m) => (
                <tr key={m.key} className="border-t border-border/60">
                  <td className="py-1 pr-2 font-sans">
                    {m.label} {m.better === "lower" ? "↓" : "↑"}
                  </td>
                  {routes.map((r) => {
                    const v = m.get(r);
                    return (
                      <td key={r.id} className="py-1 pr-2">
                        {v === null ? (
                          <span className="italic text-muted-foreground">n/a</span>
                        ) : (
                          m.format(v)
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

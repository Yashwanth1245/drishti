import * as echarts from "echarts";
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useT } from "../i18n.js";

export default function TrendsView({ meta }) {
  const t = useT();
  const el = useRef(null);
  const chartRef = useRef(null);
  const [district, setDistrict] = useState("");
  const [head, setHead] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    const qs = new URLSearchParams({ months: 36 });
    if (district) qs.set("district_id", district);
    if (head) qs.set("head_id", head);
    api(`/api/trends?${qs}`).then(setData).catch(console.error);
  }, [district, head]);

  useEffect(() => {
    if (!data || !el.current) return;
    const chart = chartRef.current ?? echarts.init(el.current, "dark",
      { renderer: "canvas" });
    chartRef.current = chart;
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: data.series.map((r) => r.month) },
      yAxis: { type: "value", name: "cases / month" },
      series: [{
        name: "Cases", type: "line", smooth: true, showSymbol: false,
        data: data.series.map((r) => r.n),
        lineStyle: { width: 2.5, color: "#4ea1ff" },
        areaStyle: { color: "rgba(78,161,255,0.12)" },
        markLine: {
          silent: true, symbol: "none",
          data: [{ yAxis: data.monthly_baseline, name: "baseline" }],
          lineStyle: { color: "#8b98a9", type: "dashed" },
          label: { formatter: "baseline", color: "#8b98a9" },
        },
      }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [data]);

  return (
    <div className="pad">
      <h2 className="pagetitle">{t("trends.title")}</h2>
      <div className="filters">
        <select value={district} onChange={(e) => setDistrict(e.target.value)}>
          <option value="">{t("trends.allka")}</option>
          {meta.districts.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={head} onChange={(e) => setHead(e.target.value)}>
          <option value="">{t("map.allheads")}</option>
          {meta.heads.map((h) => (
            <option key={h.id} value={h.id}>{h.name}</option>
          ))}
        </select>
      </div>
      <div className="card">
        <div ref={el} style={{ width: "100%", height: 380 }} />
      </div>
      {data && data.spikes.length > 0 && (
        <div className="card">
          <h3>{t("trends.spikes")}</h3>
          {data.spikes.slice(0, 12).map((s, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <span className="chip danger">z {s.zscore}</span> {s.summary}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

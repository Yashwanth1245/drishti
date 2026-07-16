import cytoscape from "cytoscape";
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { go } from "../App.jsx";

// Network lens: the ego graph around one entity. Nodes are people (sized by
// case count, coloured by risk); edges are associations (co-accused / shared
// phone) that carry their evidence FIRs.
export default function NetworkView({ entityId }) {
  const el = useRef(null);
  const [info, setInfo] = useState(null);
  const [sel, setSel] = useState(null);
  const [top, setTop] = useState(null);

  useEffect(() => {
    setInfo(null);
    setSel(null);
    if (!entityId) {
      // Landing view: association DISCOVERY — the most-connected offenders
      // statewide, so investigators find organized groups without already
      // holding a suspect name (the challenge's "association detection").
      api("/api/network/top").then((r) => setTop(r.groups)).catch(console.error);
      return;
    }
    api(`/api/network/entity/${entityId}`).then(setInfo).catch(console.error);
  }, [entityId]);

  useEffect(() => {
    if (!info || !el.current) return;
    const riskColor = (r) => r >= 55 ? "#ff5d5d" : r >= 35 ? "#f0a832" : "#3fb96f";
    const cy = cytoscape({
      container: el.current,
      maxZoom: 1.6,           // stop a lone node from filling the viewport
      minZoom: 0.2,
      elements: [
        ...info.nodes.map((n) => ({
          data: {
            id: String(n.entity_id), label: n.canonical_name,
            size: 22 + 6 * Math.min(n.n_cases, 8),
            color: n.entity_id === info.center ? "#4ea1ff" : riskColor(n.risk_score || 0),
          },
        })),
        ...info.edges.map((e) => ({
          data: {
            id: `${e.src_id}-${e.dst_id}`, source: String(e.src_id),
            target: String(e.dst_id), label: `${e.edge_type} ×${e.weight}`,
            width: 1 + Math.min(e.weight, 6),
          },
        })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": "data(color)", label: "data(label)",
          color: "#e6edf3", "font-size": 11, width: "data(size)",
          height: "data(size)", "text-valign": "bottom", "text-margin-y": 4,
          "border-width": 2, "border-color": "#0d1117" } },
        { selector: "edge", style: {
          "line-color": "#3a4658", width: "data(width)",
          "curve-style": "bezier", label: "data(label)", "font-size": 9,
          color: "#8b98a9", "text-rotation": "autorotate" } },
        { selector: ":selected", style: { "border-color": "#4ea1ff", "line-color": "#4ea1ff" } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 110 },
    });
    cy.ready(() => { cy.fit(undefined, 60); if (cy.zoom() > 1.4) cy.zoom(1.4); cy.center(); });
    cy.on("tap", "node", (evt) => {
      const id = evt.target.id();
      const node = info.nodes.find((n) => String(n.entity_id) === id);
      setSel({ type: "node", node });
    });
    cy.on("tap", "edge", (evt) => {
      const [s, t] = evt.target.id().split("-");
      const edge = info.edges.find((e) =>
        String(e.src_id) === s && String(e.dst_id) === t);
      setSel({ type: "edge", edge });
    });
    cy.on("dbltap", "node", (evt) => go(`/entity/${evt.target.id()}`));
    return () => cy.destroy();
  }, [info]);

  if (!entityId) {
    if (!top) return <div className="loading">Finding organized groups…</div>;
    return (
      <div className="pad">
        <h2 className="pagetitle">Criminal networks
          <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>
            most-connected offenders statewide · resolved by entity resolution
            · pick one to open their association graph
          </span>
        </h2>
        <div className="netgrid">
          {top.map((g, i) => (
            <div key={g.entity_id} className="card netcard"
                 onClick={() => go(`/network/${g.entity_id}`)}>
              <div className="rank">#{i + 1}</div>
              <div>
                <b>{g.canonical_name}</b>
                <div className="muted" style={{ fontSize: 12 }}>
                  {g.home_district || "—"} · {g.n_cases} case{g.n_cases > 1 && "s"}
                  · risk {g.risk_score ?? "—"}
                </div>
              </div>
              <div className="deg">
                <div className="v">{g.degree}</div>
                <div className="l">known associates</div>
              </div>
            </div>
          ))}
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          Or search any offender above and open “View network” from their
          profile.
        </div>
      </div>
    );
  }
  if (!info) return <div className="loading">Building network…</div>;

  return (
    <div className="netwrap">
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      <div className="map-side">
        <div className="card">
          <h3>Criminal network</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            {info.nodes.length} entities, {info.edges.length} associations.
            Node size = cases, colour = risk. Click for detail, double-click to
            open a profile.
          </div>
        </div>
        {sel?.type === "node" && (
          <div className="card">
            <h3>{sel.node.canonical_name}</h3>
            <div>{sel.node.n_cases} cases · risk {sel.node.risk_score ?? "—"}</div>
            <a onClick={() => go(`/entity/${sel.node.entity_id}`)}>Open profile →</a>
          </div>
        )}
        {sel?.type === "edge" && (
          <div className="card">
            <h3>{sel.edge.edge_type}</h3>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
              Shared in {sel.edge.weight} case(s):
            </div>
            {sel.edge.evidence.map((cn) => (
              <span key={cn} className="chip mono accent rowlink"
                    onClick={() => go(`/case/${cn}`)}>{cn}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

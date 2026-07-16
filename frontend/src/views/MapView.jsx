import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import React, { useEffect, useRef, useState } from "react";
import { api, fmt } from "../api.js";

const BASE_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [{ id: "base", type: "raster", source: "carto" }],
};

const HOUR_BANDS = ["", "00-03", "03-06", "06-09", "09-12", "12-15",
                    "15-18", "18-21", "21-24"];

// District/station circles are rendered as GeoJSON circle LAYERS (anchored in
// map coordinates) — not HTML markers — so they stay pinned to their exact
// location at every zoom level. Spike districts get an animated glow layer.
export default function MapView({ meta }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const [head, setHead] = useState("");
  const [hourBand, setHourBand] = useState("");
  const [districts, setDistricts] = useState([]);
  const [picked, setPicked] = useState(null);
  const [stations, setStations] = useState(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const coordOf = useRef({});

  useEffect(() => {
    meta.districts.forEach((d) => (coordOf.current[d.id] = [d.lon, d.lat]));
    const map = new maplibregl.Map({
      container: mapEl.current, style: BASE_STYLE,
      center: [76.4, 15.0], zoom: 6.1, attributionControl: { compact: true },
      maxBounds: [[72.5, 10.5], [80.5, 19.5]],
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      map.addSource("districts", emptyFC());
      map.addSource("dspike", emptyFC());
      map.addSource("stations", emptyFC());
      // pulsing glow under spike districts
      map.addLayer({
        id: "dspike-glow", type: "circle", source: "dspike",
        paint: { "circle-color": "#ff5d5d", "circle-opacity": 0.25,
                 "circle-radius": ["get", "r"] },
      });
      // district volume circles
      map.addLayer({
        id: "district-fill", type: "circle", source: "districts",
        paint: {
          "circle-radius": ["get", "r"],
          "circle-color": ["case", ["get", "spike"], "#ff5d5d", "#4ea1ff"],
          "circle-opacity": 0.4,
          "circle-stroke-width": 1.4,
          "circle-stroke-color": ["case", ["get", "spike"], "#ff8f8f", "#7fbfff"],
        },
      });
      // (district name labels come from the CARTO basemap + click popups +
      // the side panel — no custom glyph font dependency to fail on stage)
      // station circles (shown after drill-down)
      map.addLayer({
        id: "station-fill", type: "circle", source: "stations",
        paint: {
          "circle-radius": ["get", "r"], "circle-color": "#ff5d5d",
          "circle-opacity": 0.6, "circle-stroke-color": "#ff8f8f",
          "circle-stroke-width": 1,
        },
      });

      const hover = new maplibregl.Popup({
        closeButton: false, closeOnClick: false, offset: 10 });
      map.on("mousemove", "district-fill", (e) => {
        const p = e.features[0].properties;
        hover.setLngLat(e.lngLat)
          .setHTML(`<b>${p.name}</b> · ${Number(p.n).toLocaleString("en-IN")} cases`
                   + (p.spike ? ` · <span style="color:#ff5d5d">spike</span>` : ""))
          .addTo(map);
      });
      map.on("mouseleave", "district-fill", () => hover.remove());
      map.on("click", "district-fill", (e) => {
        const p = e.features[0].properties;
        pickDistrict(districtsRef.current.find((d) => d.district_id === p.district_id));
      });
      map.on("click", "station-fill", (e) => {
        const p = e.features[0].properties;
        new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat)
          .setHTML(`<b>${p.name}</b><br/>${p.n} cases`).addTo(map);
      });
      for (const lyr of ["district-fill", "station-fill"]) {
        map.on("mouseenter", lyr, () => map.getCanvas().style.cursor = "pointer");
        map.on("mouseleave", lyr, () => map.getCanvas().style.cursor = "");
      }
      readyRef.current = true;
      renderDistricts(districtsRef.current);
      // animated pulse: grow + fade the glow radius each frame
      const t0 = performance.now();
      const animate = (now) => {
        if (!mapRef.current) return;
        const f = ((now - t0) % 1500) / 1500;      // 0..1
        if (map.getLayer("dspike-glow")) {
          map.setPaintProperty("dspike-glow", "circle-radius",
            ["*", ["get", "r"], 1 + 1.4 * f]);
          map.setPaintProperty("dspike-glow", "circle-opacity", 0.3 * (1 - f));
        }
        requestAnimationFrame(animate);
      };
      requestAnimationFrame(animate);
    });
    mapRef.current = map;
    return () => { mapRef.current = null; map.remove(); };
  }, []);           // eslint-disable-line react-hooks/exhaustive-deps

  const districtsRef = useRef([]);
  useEffect(() => { districtsRef.current = districts; renderDistricts(districts); },
    [districts]);

  useEffect(() => {
    // Hour band applies at EVERY level — the state view re-weighs its
    // circles too (the challenge's "layering time of day with location").
    const qs = new URLSearchParams();
    if (head) qs.set("head_id", head);
    if (hourBand) qs.set("hour_band", hourBand);
    api(`/api/map/districts${qs.size ? `?${qs}` : ""}`)
      .then((d) => setDistricts(d.districts)).catch(console.error);
  }, [head, hourBand]);

  // Keep the drill-down in LOCKSTEP with the filters: whenever the district
  // numbers refresh (crime-head or hour change), re-sync the picked card
  // from the fresh row (its count changes too) and refetch its station
  // layer — without re-flying the camera. Station-rank officers land
  // straight in their district (the lone circle tells them nothing).
  useEffect(() => {
    if (picked) {
      const fresh = districts.find((d) => d.district_id === picked.district_id);
      if (fresh) pickDistrict(fresh, false);
    } else if (meta.scope?.station_id && districts.length === 1) {
      pickDistrict(districts[0]);
    }
  }, [districts]);       // eslint-disable-line react-hooks/exhaustive-deps

  function renderDistricts(list) {
    const map = mapRef.current;
    if (!map || !readyRef.current || !list.length) return;
    const maxN = Math.max(...list.map((d) => d.n), 1);
    const feat = (d) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: coordOf.current[d.district_id] },
      properties: {
        district_id: d.district_id, name: d.name, n: d.n,
        spike: !!d.has_spike_alert,
        r: 8 + 30 * Math.sqrt(d.n / maxN),
      },
    });
    map.getSource("districts").setData({
      type: "FeatureCollection", features: list.map(feat),
    });
    map.getSource("dspike").setData({
      type: "FeatureCollection",
      features: list.filter((d) => d.has_spike_alert).map(feat),
    });
  }

  async function pickDistrict(d, fly = true) {
    if (!d) return;
    setPicked(d);
    setStations(null);
    if (fly) mapRef.current.flyTo({ center: coordOf.current[d.district_id],
                                    zoom: 8.4 });
    const qs = new URLSearchParams({ district_id: d.district_id });
    if (head) qs.set("head_id", head);
    if (hourBand) qs.set("hour_band", hourBand);
    const r = await api(`/api/map/stations?${qs}`);
    setStations(r.stations);
    drawStations(r.stations);
  }

  function drawStations(list) {
    const map = mapRef.current;
    if (!map?.getSource("stations")) return;
    const maxN = Math.max(1, ...list.map((s) => s.n));
    map.getSource("stations").setData({
      type: "FeatureCollection",
      features: list.filter((s) => s.n > 0).map((s) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
        properties: { name: s.name, n: s.n,
                      r: 4 + 12 * Math.sqrt(s.n / maxN) },
      })),
    });
  }


  function clearDrill() {
    setPicked(null);
    setStations(null);
    mapRef.current?.getSource("stations")?.setData(emptyFC().data);
    mapRef.current?.flyTo({ center: [76.4, 15.0], zoom: 6.1 });
  }

  const top = [...districts].sort((a, b) => b.rate_per_lakh - a.rate_per_lakh)
    .slice(0, 8);

  // The control panel overlays the map, so it must be dismissible — an
  // officer studying north Karnataka should not have a card in the way.
  if (!panelOpen) return (
    <div className="mapwrap">
      <div ref={mapEl} className="map" />
      <button className="map-side-open" onClick={() => setPanelOpen(true)}>
        ☰ Map controls
        {(head || hourBand) && <span className="dot" title="filters active" />}
      </button>
    </div>
  );

  return (
    <div className="mapwrap">
      <div ref={mapEl} className="map" />
      <div className="map-side">
        <div className="card">
          <h3>Command map
            <a className="panel-toggle" onClick={() => setPanelOpen(false)}>
              hide ⟨
            </a>
          </h3>
          <div className="filters">
            <select value={head} onChange={(e) => setHead(e.target.value)}>
              <option value="">All crime heads</option>
              {meta.heads.map((h) => (
                <option key={h.id} value={h.id}>{h.name}</option>
              ))}
            </select>
            <select value={hourBand} onChange={(e) => setHourBand(e.target.value)}>
              {HOUR_BANDS.map((b) => (
                <option key={b} value={b}>{b ? `${b} hrs` : "All hours"}</option>
              ))}
            </select>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            Circle size = case volume · <span style={{ color: "var(--danger)" }}>
            pulsing red = the hottest spike zones</span>
            {head ? " in this crime head" : ""}. Click a district to drill in.
          </div>
        </div>

        {picked ? (
          <div className="card">
            <h3>{picked.name}
              <a style={{ float: "right", fontSize: 12 }}
                 onClick={clearDrill}>← state view</a></h3>
            <div>{fmt(picked.n)} cases · {picked.rate_per_lakh}/lakh</div>
            {picked.has_spike_alert && (
              <>
                <div className="chip danger" style={{ marginTop: 6 }}>
                  spike · z {picked.spike_z}
                </div>
                {picked.spike_summary && (
                  <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                    {picked.spike_summary}
                  </div>
                )}
              </>
            )}
            {stations ? (
              <>
                <table className="t" style={{ marginTop: 8 }}>
                  <thead><tr><th>Station</th>
                    <th style={{ textAlign: "right" }}
                        title="FIRs registered at this station under the current filters">
                      FIRs</th></tr></thead>
                  <tbody>
                    {[...stations].sort((a, b) => b.n - a.n).slice(0, 10).map((s) => (
                      <tr key={s.unit_id}><td>{s.name}</td>
                        <td style={{ textAlign: "right" }}>{s.n}</td></tr>
                    ))}
                  </tbody>
                </table>
                {meta.scope?.station_id && (
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    Station-wise detail is limited to your station at this
                    rank; district totals are aggregate context.
                  </div>
                )}
              </>
            ) : <div className="loading">Loading stations…</div>}
          </div>
        ) : (
          <div className="card">
            <h3>Highest rate per lakh</h3>
            <table className="t">
              <tbody>
                {top.map((d) => (
                  <tr key={d.district_id} className="rowlink"
                      onClick={() => pickDistrict(d)}>
                    <td>{d.name}{d.has_spike_alert &&
                      <span className="chip danger" style={{ marginLeft: 6 }}
                            title={d.spike_summary || ""}>spike</span>}</td>
                    <td style={{ textAlign: "right" }}>{d.rate_per_lakh}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function emptyFC() {
  return { type: "geojson", data: { type: "FeatureCollection", features: [] } };
}

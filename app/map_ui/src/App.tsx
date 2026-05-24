import React, { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import { AlertTriangle, Box, Database, Droplets, MapPinned, MessageSquare, Route, Send, ShieldAlert, Thermometer, Warehouse } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type FeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: Record<string, unknown>;
    geometry: Record<string, unknown>;
  }>;
};

type SummaryRow = {
  entity_type: string;
  count: number;
};

type RiskSummaryRow = {
  severity: string | null;
  event_type: string;
  count: number;
};

type ToolResult = {
  tool: string;
  count: number;
  features: FeatureCollection["features"];
  explanation: string;
  confidence: number;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const INITIAL_VIEW_STATE = {
  longitude: -74.22,
  latitude: 41.05,
  zoom: 6.2,
  pitch: 25,
  bearing: 0
};

const layerColors: Record<string, [number, number, number, number]> = {
  port: [32, 117, 153, 230],
  facility: [184, 96, 54, 220],
  route: [58, 124, 79, 210],
  location: [20, 160, 160, 200],
  risk: [207, 74, 58, 110]
};

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function titleize(value: unknown) {
  return String(value ?? "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function tooltipHtml(props: Record<string, unknown>) {
  const isRiskEvent = props.record_type === "risk_event" || Boolean(props.event_type);
  const isRiskScore = props.record_type === "risk_score";
  const title = isRiskEvent
    ? props.headline || props.event_type || "NOAA alert"
    : props.name || props.subtype || props.entity_type || "Supply-chain entity";
  const rows = isRiskEvent
    ? [
        ["Type", props.event_type],
        ["Severity", props.severity],
        ["Area", props.area_desc],
        ["Source", props.source_name],
        ["ID", props.source_event_id]
      ]
    : isRiskScore
    ? [
        ["Type", titleize(props.entity_type)],
        ["Risk score", props.risk_score],
        ["Top severity", props.top_severity],
        ["Alerts", props.impact_count],
        ["Source", props.source_name]
      ]
    : [
        ["Type", titleize(props.entity_type)],
        ["Subtype", props.subtype],
        ["Source", props.source_name],
        ["ID", props.source_entity_id]
      ];
  const detail = rows
    .filter(([, value]) => value)
    .map(([label, value]) => `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`)
    .join("");

  return `<div class="map-tooltip"><h2>${escapeHtml(title)}</h2><div>${detail}</div></div>`;
}

function useGeoJson(entityType: string, enabled = true, subtype?: string) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ entity_type: entityType, limit: "25000" });
    if (subtype) params.set("subtype", subtype);
    fetch(`${API_BASE_URL}/geo/entities?${params}`)
      .then((response) => response.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [enabled, entityType, subtype]);

  return { data, loading };
}

function useRiskEvents(enabled = true) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/events?limit=1000`)
      .then((response) => response.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [enabled]);

  return { data, loading };
}

function useSummary() {
  const [summary, setSummary] = useState<SummaryRow[]>([]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/geo/summary`)
      .then((response) => response.json())
      .then(setSummary)
      .catch(() => setSummary([]));
  }, []);

  return summary;
}

function useRiskImpacts(eventId: string | null) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!eventId) {
      setData({ type: "FeatureCollection", features: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/events/${eventId}/impacts?limit=5000`)
      .then((response) => response.json())
      .then(setData)
      .catch(() => setData({ type: "FeatureCollection", features: [] }))
      .finally(() => setLoading(false));
  }, [eventId]);

  return { data, loading };
}

function riskScoreColor(score: number): [number, number, number, number] {
  if (score >= 6) return [207, 52, 40, 240];
  if (score >= 3) return [230, 130, 30, 230];
  if (score >= 1) return [210, 185, 30, 220];
  return [55, 170, 65, 210];
}

function useRiskScores(enabled = true) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setData({ type: "FeatureCollection", features: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/scores?limit=5000`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ type: "FeatureCollection", features: [] }))
      .finally(() => setLoading(false));
  }, [enabled]);

  return { data, loading };
}

function useRiskSummary() {
  const [summary, setSummary] = useState<RiskSummaryRow[]>([]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/risk/summary`)
      .then((response) => response.json())
      .then(setSummary)
      .catch(() => setSummary([]));
  }, []);

  return summary;
}

export function App() {
  const [selectedRiskEventId, setSelectedRiskEventId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatToolResult, setChatToolResult] = useState<ToolResult | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const [visibleLayers, setVisibleLayers] = useState({
    routes: true,
    facilities: true,
    ports: true,
    alerts: true,
    riskScores: false,
    weatherStations: false,
    streamGauges: false,
  });

  const ports = useGeoJson("port", visibleLayers.ports);
  const facilities = useGeoJson("facility", visibleLayers.facilities);
  const routes = useGeoJson("route", visibleLayers.routes);
  const weatherStations = useGeoJson("location", visibleLayers.weatherStations, "weather_station");
  const streamGauges = useGeoJson("location", visibleLayers.streamGauges, "stream_gauge");
  const riskEvents = useRiskEvents(visibleLayers.alerts);
  const riskImpacts = useRiskImpacts(selectedRiskEventId);
  const riskScores = useRiskScores(visibleLayers.riskScores);
  const summary = useSummary();
  const riskSummary = useRiskSummary();
  const activeRiskCount = riskSummary.reduce((total, item) => total + item.count, 0);
  const routeCount = summary.find((item) => item.entity_type === "route")?.count ?? 0;
  const facilityCount = summary.find((item) => item.entity_type === "facility")?.count ?? 0;
  const portCount = summary.find((item) => item.entity_type === "port")?.count ?? 0;

  useEffect(() => {
    chatEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [chatMessages, chatLoading]);

  async function sendChat() {
    const content = chatInput.trim();
    if (!content || chatLoading) return;

    const newMessages: ChatMessage[] = [...chatMessages, { role: "user", content }];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);

    try {
      const resp = await fetch(`${API_BASE_URL}/tools/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newMessages,
          active_layers: Object.entries(visibleLayers)
            .filter(([, v]) => v)
            .map(([k]) => k),
        }),
      });
      const data = await resp.json() as {
        response: string;
        tool_used: string | null;
        tool_result: ToolResult | null;
      };
      setChatMessages([...newMessages, { role: "assistant", content: data.response }]);
      if (data.tool_result) {
        setChatToolResult(data.tool_result);
      }
    } catch {
      setChatMessages([...newMessages, {
        role: "assistant",
        content: "Sorry, I couldn't reach the server. Please try again."
      }]);
    } finally {
      setChatLoading(false);
    }
  }

  const layers = useMemo(() => {
    const osmTiles = new TileLayer({
      id: "osm-base-tiles",
      data: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      minZoom: 0,
      maxZoom: 19,
      tileSize: 256,
      renderSubLayers: (props) => {
        const tile = props.tile as unknown as {
          bbox?: { west: number; south: number; east: number; north: number };
          boundingBox?: [[number, number], [number, number]];
        };
        const bounds = tile.bbox
          ? [tile.bbox.west, tile.bbox.south, tile.bbox.east, tile.bbox.north]
          : [
              tile.boundingBox?.[0][0] ?? 0,
              tile.boundingBox?.[0][1] ?? 0,
              tile.boundingBox?.[1][0] ?? 0,
              tile.boundingBox?.[1][1] ?? 0
            ];
        return new BitmapLayer(props, {
          data: undefined,
          image: props.data,
          bounds: bounds as never
        });
      }
    });

    const routeLayer = new GeoJsonLayer({
      id: "routes",
      data: routes.data as never,
      pickable: true,
      stroked: true,
      filled: false,
      lineWidthMinPixels: 1,
      getLineColor: layerColors.route,
      getLineWidth: 2
    });

    const facilityLayer = new GeoJsonLayer({
      id: "facilities",
      data: facilities.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 3,
      getFillColor: layerColors.facility,
      getLineColor: [118, 64, 40, 230],
      getLineWidth: 1
    });

    const portLayer = new GeoJsonLayer({
      id: "ports",
      data: ports.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 5,
      getFillColor: layerColors.port,
      getLineColor: [12, 72, 104, 240],
      getLineWidth: 1
    });

    const weatherStationLayer = new GeoJsonLayer({
      id: "weather-stations",
      data: weatherStations.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 4,
      getFillColor: layerColors.location,
      getLineColor: [10, 110, 110, 230],
      getLineWidth: 1
    });

    const streamGaugeLayer = new GeoJsonLayer({
      id: "stream-gauges",
      data: streamGauges.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 3,
      getFillColor: [30, 130, 180, 200],
      getLineColor: [10, 80, 130, 230],
      getLineWidth: 1
    });

    const riskLayer = new GeoJsonLayer({
      id: "risk-events",
      data: riskEvents.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      getFillColor: layerColors.risk,
      getLineColor: [154, 45, 39, 220],
      getLineWidth: 2,
      lineWidthMinPixels: 1
    });

    const riskImpactLayer = selectedRiskEventId
      ? new GeoJsonLayer({
          id: "risk-impacts",
          data: riskImpacts.data as never,
          pickable: true,
          stroked: true,
          filled: true,
          pointRadiusMinPixels: 8,
          getFillColor: [245, 194, 66, 230],
          getLineColor: [132, 89, 12, 255],
          getLineWidth: 3,
          lineWidthMinPixels: 2
        })
      : null;

    const riskScoreLayer = visibleLayers.riskScores
      ? new GeoJsonLayer({
          id: "risk-scores",
          data: riskScores.data as never,
          pickable: true,
          filled: true,
          stroked: true,
          pointRadiusMinPixels: 5,
          getFillColor: (f: { properties: { risk_score?: number } }) =>
            riskScoreColor(f.properties.risk_score ?? 0),
          getLineColor: [60, 20, 20, 180],
          getLineWidth: 2,
          lineWidthMinPixels: 1,
          updateTriggers: { getFillColor: [riskScores.data] },
        })
      : null;

    const chatResultLayer = chatToolResult && chatToolResult.count > 0
      ? new GeoJsonLayer({
          id: "chat-results",
          data: { type: "FeatureCollection", features: chatToolResult.features } as never,
          pickable: true,
          filled: true,
          stroked: true,
          pointRadiusMinPixels: 9,
          getFillColor: [255, 200, 0, 230],
          getLineColor: [160, 120, 0, 255],
          getLineWidth: 2,
          lineWidthMinPixels: 2,
        })
      : null;

    return [
      osmTiles,
      visibleLayers.routes ? routeLayer : null,
      visibleLayers.alerts ? riskLayer : null,
      riskImpactLayer,
      riskScoreLayer,
      visibleLayers.weatherStations ? weatherStationLayer : null,
      visibleLayers.streamGauges ? streamGaugeLayer : null,
      visibleLayers.facilities ? facilityLayer : null,
      visibleLayers.ports ? portLayer : null,
      chatResultLayer,
    ].filter(Boolean);
  }, [facilities.data, weatherStations.data, streamGauges.data, ports.data, riskEvents.data, riskImpacts.data, riskScores.data, routes.data, selectedRiskEventId, visibleLayers, chatToolResult]);

  const isLoading =
    ports.loading || facilities.loading || routes.loading || weatherStations.loading || streamGauges.loading || riskEvents.loading || riskImpacts.loading || riskScores.loading;
  const setLayerVisibility = (layer: keyof typeof visibleLayers, value: boolean) => {
    setVisibleLayers((current) => ({ ...current, [layer]: value }));
  };

  return (
    <main>
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller
        layers={layers}
        getTooltip={({ object }) => {
          if (!object) return null;
          const props = object.properties ?? {};
          return { html: tooltipHtml(props) };
        }}
        onClick={({ object }) => {
          if (!object) return;
          const props = object.properties ?? {};
          if (props.record_type === "risk_event") {
            setSelectedRiskEventId(String(object.id));
          }
        }}
      />

      <aside className="panel">
        <div className="title-row">
          <MapPinned size={20} aria-hidden />
          <h1>Open Supply Chain</h1>
        </div>
        <div className="aoi">NY + NJ + CT AOI</div>

        <section className="layer-list">
          <LayerCard icon={<Route size={17} />} label="Routes" value={routeCount} active={visibleLayers.routes} onClick={() => setLayerVisibility("routes", !visibleLayers.routes)} />
          <LayerCard icon={<Warehouse size={17} />} label="Facilities" value={facilityCount} active={visibleLayers.facilities} onClick={() => setLayerVisibility("facilities", !visibleLayers.facilities)} />
          <LayerCard icon={<Box size={17} />} label="Ports" value={portCount} active={visibleLayers.ports} onClick={() => setLayerVisibility("ports", !visibleLayers.ports)} />
          <LayerCard icon={<AlertTriangle size={17} />} label="Active Alerts" value={activeRiskCount} active={visibleLayers.alerts} onClick={() => setLayerVisibility("alerts", !visibleLayers.alerts)} />
          <LayerCard
            icon={<ShieldAlert size={17} />}
            label="Risk Scores"
            value={riskScores.data.features.length}
            active={visibleLayers.riskScores}
            onClick={() => setLayerVisibility("riskScores", !visibleLayers.riskScores)}
          />
          <LayerCard
            icon={<Thermometer size={17} />}
            label="Weather Stations"
            value={weatherStations.data.features.length}
            active={visibleLayers.weatherStations}
            onClick={() => setLayerVisibility("weatherStations", !visibleLayers.weatherStations)}
            secondary
          />
          <LayerCard
            icon={<Droplets size={17} />}
            label="Stream Gauges"
            value={streamGauges.data.features.length}
            active={visibleLayers.streamGauges}
            onClick={() => setLayerVisibility("streamGauges", !visibleLayers.streamGauges)}
            secondary
          />
        </section>

        {selectedRiskEventId && (
          <section className="impact-summary">
            <div className="impact-summary-label">
              <AlertTriangle size={13} aria-hidden />
              <span>Impact Network</span>
            </div>
            <strong>{riskImpacts.data.features.length.toLocaleString()} linked assets</strong>
            <span>{riskImpacts.loading ? "Loading persisted impact edges..." : "Stored from risk_impacts evidence"}</span>
          </section>
        )}

        <section className="chat-panel">
          <div className="chat-panel-label">
            <MessageSquare size={13} aria-hidden />
            <span>Ask the supply chain</span>
          </div>

          <div className="chat-messages">
            {chatMessages.length === 0 && (
              <div className="chat-empty">
                Ask about ports, facilities, routes, or weather — e.g. "ports near Newark" or "warehouses within 20km of JFK"
              </div>
            )}
            {chatMessages.map((msg, i) => (
              <div key={i} className={`chat-bubble chat-bubble--${msg.role}`}>
                {msg.content}
              </div>
            ))}
            {chatLoading && (
              <div className="chat-bubble chat-bubble--assistant chat-bubble--thinking">
                Thinking…
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {chatToolResult && chatToolResult.count > 0 && (
            <div className="chat-result-badge">
              {chatToolResult.count.toLocaleString()} results on map · {chatToolResult.tool.replace(/_/g, " ")}
            </div>
          )}

          <div className="chat-input-row">
            <input
              className="chat-input"
              type="text"
              placeholder="Ask about the supply chain…"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendChat();
                }
              }}
              disabled={chatLoading}
            />
            <button
              className="chat-send"
              onClick={sendChat}
              disabled={chatLoading || chatInput.trim().length === 0}
              aria-label="Send"
            >
              <Send size={14} />
            </button>
          </div>
        </section>

        <div className="source-row">
          <Database size={16} aria-hidden />
          <span>{isLoading ? "Loading canonical layers" : "Serving canonical GeoJSON from FastAPI"}</span>
        </div>
      </aside>

      <footer>
        Map data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>
      </footer>
    </main>
  );
}

function LayerCard({
  icon,
  label,
  value,
  active,
  onClick,
  secondary = false
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  active: boolean;
  onClick: () => void;
  secondary?: boolean;
}) {
  return (
    <button
      type="button"
      className={`layer-card${active ? " is-active" : ""}${secondary ? " is-secondary" : ""}`}
      aria-pressed={active}
      onClick={onClick}
    >
      <span className="layer-card-label">
        {icon}
        <span>{label}</span>
      </span>
      <strong>{value.toLocaleString()}</strong>
    </button>
  );
}

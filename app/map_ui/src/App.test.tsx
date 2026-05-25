import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("@deck.gl/react", () => ({
  default: ({ layers, onClick }: { layers: unknown[]; onClick?: (info: { object: unknown }) => void }) => (
    <button
      data-layer-count={layers.length}
      data-testid="deckgl"
      onClick={() =>
        onClick?.({
          object: {
            id: "alert-1",
            properties: { record_type: "risk_event", event_type: "Rip Current Statement" }
          }
        })
      }
      type="button"
    >
      deck
    </button>
  )
}));

vi.mock("@deck.gl/layers", () => ({
  GeoJsonLayer: class GeoJsonLayer {
    constructor(public props: Record<string, unknown>) {}
  },
  BitmapLayer: class BitmapLayer {
    constructor(
      public props: Record<string, unknown>,
      public layerProps: Record<string, unknown>
    ) {}
  }
}));

vi.mock("@deck.gl/geo-layers", () => ({
  TileLayer: class TileLayer {
    constructor(public props: Record<string, unknown>) {}
  }
}));

const emptyCollection = { type: "FeatureCollection", features: [] };

function expectLayerValue(label: string, value: string) {
  const layerButton = screen.getByRole("button", { name: new RegExp(`${label}\\s+${value}`) });
  expect(within(layerButton).getByText(value)).toBeInTheDocument();
}

describe("App", () => {
  beforeEach(() => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/geo/summary")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve([
              { entity_type: "port", count: 224 },
              { entity_type: "facility", count: 3 },
              { entity_type: "route", count: 2 },
              { entity_type: "location", count: 1910 }
            ])
        });
      }
      if (url.includes("/risk/summary")) {
        return Promise.resolve({
          json: () => Promise.resolve([{ severity: "Moderate", event_type: "Rip Current Statement", count: 5 }])
        });
      }
      if (url.includes("/risk/events/alert-1/impacts")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  id: "port-1",
                  properties: {
                    entity_type: "port",
                    name: "Test Port",
                    impact_method: "intersects"
                  },
                  geometry: { type: "Point", coordinates: [-74, 40.7] }
                }
              ]
            })
        });
      }
      if (url.includes("/risk/events?limit=1000")) {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              type: "FeatureCollection",
              features: Array.from({ length: 5 }, (_, index) => ({
                type: "Feature",
                id: `alert-${index + 1}`,
                properties: {
                  record_type: "risk_event",
                  event_type: index === 0 ? "Rip Current Statement" : `Coastal Flood Warning ${index + 1}`,
                  severity: index % 2 === 0 ? "Moderate" : "Minor"
                },
                geometry: { type: "Point", coordinates: [-74 + index * 0.1, 40.7] }
              }))
            })
        });
      }

      return Promise.resolve({
        json: () => Promise.resolve(emptyCollection)
      });
    });

    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches canonical layers and renders summary counts", async () => {
    render(<App />);

    expect(screen.getByText("Open Supply Chain")).toBeInTheDocument();
    expect(screen.getByText("Synchronizing operational model")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask the network...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Scenario/ })).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText("Model synchronized from governed spatial tools")).toBeInTheDocument()
    );

    expectLayerValue("Infrastructure nodes", "3");
    expectLayerValue("Movement corridors", "2");
    expectLayerValue("Operational pressure", "5");
    expect(screen.getByRole("button", { name: /Additional intelligence\s+Show/ })).toBeInTheDocument();
    expect(screen.getByText("Operational pressure increasing along the Atlantic corridor")).toBeInTheDocument();
    expect(screen.getByText("5 live pressure signals are shaping the current view.")).toBeInTheDocument();
    expect(screen.getByText("Rip Current Statement")).toBeInTheDocument();
    expect(screen.queryByText("Coastal Flood Warning 5")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View all signals (5)" })).toBeInTheDocument();
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.getAllByText("Moderate").length).toBeGreaterThan(0);
    expect(screen.getByTestId("deckgl")).toHaveAttribute("data-layer-count", "6");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/geo/entities?entity_type=port&limit=25000");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/geo/entities?entity_type=facility&limit=25000");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/geo/entities?entity_type=route&limit=25000");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/risk/events?limit=1000");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/geo/stream-gauges");
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/geo/summary");
  });

  it("reveals all pressure signals on demand", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => expect(screen.getByText("Rip Current Statement")).toBeInTheDocument());
    expect(screen.queryByText("Coastal Flood Warning 5")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View all signals (5)" }));

    expect(screen.getByText("Coastal Flood Warning 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show fewer signals" })).toBeInTheDocument();
  });

  it("toggles hydrologic signals from its signal control", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByText("Model synchronized from governed spatial tools")).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: /Additional intelligence\s+Show/ }));
    await user.click(screen.getByRole("button", { name: /Hydrologic signals\s+0/ }));

    expect(screen.getByTestId("deckgl")).toHaveAttribute("data-layer-count", "5");
  });

  it("collapses the command surface into a mode rail", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByText("Model synchronized from governed spatial tools")).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(screen.queryByText("Model synchronized from governed spatial tools")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Live/ })).toBeInTheDocument();
  });

  it("loads persisted impact edges when an alert is selected", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() =>
      expect(screen.getByText("Model synchronized from governed spatial tools")).toBeInTheDocument()
    );

    await user.click(screen.getByTestId("deckgl"));

    await waitFor(() => expect(screen.getByText("1 linked assets")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/risk/events/alert-1/impacts?limit=5000");
    expect(screen.getByTestId("deckgl")).toHaveAttribute("data-layer-count", "7");
  });
});

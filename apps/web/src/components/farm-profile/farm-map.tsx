"use client";

import { Check, Map as MapIcon, MapPin, PenTool, Pencil, Satellite, Trash2, X } from "lucide-react";
import { MaplibreTerradrawControl } from "@watergis/maplibre-gl-terradraw";
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import MapView, {
  Layer,
  Marker,
  NavigationControl,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from "react-map-gl/maplibre";

import {
  fieldBoundaryCollectionResponseSchema,
  type FarmBoundary,
  type FarmBoundaryMetadata,
  type FieldBoundaryCollectionResponse,
  type FieldBoundaryFeature,
} from "@/lib/contracts";
import { summarizeFarmBoundary } from "@/lib/farm-profile/boundary";

type Coordinates = {
  latitude: number;
  longitude: number;
};

export type SelectedFarmField = {
  geometry: FarmBoundary;
  metadata: FarmBoundaryMetadata;
  areaAcres: number | null;
};

type FarmMapProps = {
  coordinates: Coordinates | null;
  selectedField: SelectedFarmField | null;
  onPointChange: (coordinates: Coordinates) => void;
  onFieldSelect: (field: SelectedFarmField, coordinates: Coordinates) => void;
  onFieldClear: () => void;
};

type BasemapMode = "standard" | "satellite";
type BoundaryStatus =
  | "zoom"
  | "loading"
  | "ready"
  | "truncated"
  | "empty"
  | "not_loaded"
  | "unavailable";
type DrawingMode = "idle" | "draw" | "edit";
type DrawInstance = NonNullable<ReturnType<MaplibreTerradrawControl["getTerraDrawInstance"]>>;
type DrawFeatureId = Parameters<DrawInstance["getSnapshotFeature"]>[0];
type BoundaryOverlay = {
  width: number;
  height: number;
  path: string;
};

const FIELD_FILL_LAYER_ID = "mapped-fields-fill";
const FIELD_OUTLINE_LAYER_ID = "mapped-fields-outline";
const SELECTED_FIELD_FILL_LAYER_ID = "selected-mapped-field-fill";
const SELECTED_FIELD_OUTLINE_LAYER_ID = "selected-mapped-field-outline";
const FIELD_MIN_ZOOM = 10.5;
const mapTilerKey = process.env.NEXT_PUBLIC_MAPTILER_KEY?.trim();

const standardStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "\u00a9 OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const satelliteStyle: StyleSpecification | null = mapTilerKey
  ? {
      version: 8,
      sources: {
        satellite: {
          type: "raster",
          tiles: [
            `https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key=${encodeURIComponent(mapTilerKey)}`,
          ],
          tileSize: 256,
          attribution: "\u00a9 MapTiler",
        },
      },
      layers: [{ id: "satellite", type: "raster", source: "satellite" }],
    }
  : null;

const emptyFieldCollection: FieldBoundaryCollectionResponse = {
  type: "FeatureCollection",
  features: [],
  available: false,
  coverage_status: "not_loaded",
  truncated: false,
  dataset_version: null,
};

function boundaryMessage(status: BoundaryStatus, selected: boolean) {
  if (selected) return "Field selected";
  if (status === "loading") return "Loading mapped fields...";
  if (status === "ready") return "Select one outlined field";
  if (status === "truncated") return "Zoom in to see every mapped field";
  if (status === "empty") return "No crop fields found in this covered area";
  if (status === "not_loaded") return "USDA mapped-field coverage is not loaded here";
  if (status === "unavailable") return "Mapped fields are temporarily unavailable";
  return "Zoom in to reveal mapped fields";
}

function roundedCoordinates(latitude: number, longitude: number) {
  return {
    latitude: Number(latitude.toFixed(6)),
    longitude: Number(longitude.toFixed(6)),
  };
}

function raiseFieldLayers(map: MapLibreMap) {
  const fieldLayerIds = [
    FIELD_FILL_LAYER_ID,
    FIELD_OUTLINE_LAYER_ID,
    SELECTED_FIELD_FILL_LAYER_ID,
    SELECTED_FIELD_OUTLINE_LAYER_ID,
  ].filter((layerId) => map.getLayer(layerId));
  if (!fieldLayerIds.length) return;

  const styleLayers = map.getStyle().layers;
  const rasterLayerIndex = styleLayers.reduce(
    (highestIndex, layer, index) => (layer.type === "raster" ? index : highestIndex),
    -1,
  );
  let previousIndex = rasterLayerIndex;
  const alreadyAboveBasemap = fieldLayerIds.every((layerId) => {
    const index = styleLayers.findIndex((layer) => layer.id === layerId);
    const correctlyPlaced = index > previousIndex;
    previousIndex = index;
    return correctlyPlaced;
  });
  if (alreadyAboveBasemap) return;

  for (const layerId of fieldLayerIds) {
    map.moveLayer(layerId);
  }
}

function projectBoundaryOverlay(
  map: MapLibreMap,
  geometry: FarmBoundary,
): BoundaryOverlay | null {
  const canvas = map.getCanvas();
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return null;

  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const path = polygons
    .flatMap((polygon) => polygon)
    .map((ring) => {
      const points = ring.map(([longitude, latitude]) => map.project([longitude, latitude]));
      if (!points.length) return "";
      return `${points
        .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
        .join(" ")} Z`;
    })
    .filter(Boolean)
    .join(" ");

  return path ? { width, height, path } : null;
}

function displayedFieldCollection(
  collection: FieldBoundaryCollectionResponse,
  selectedField: SelectedFarmField | null,
): FieldBoundaryCollectionResponse {
  const selectedId = selectedField?.metadata.source_id;
  if (!selectedField || !selectedId) return collection;
  if (collection.features.some((feature) => feature.properties.field_id === selectedId)) {
    return collection;
  }

  const selectedFeature: FieldBoundaryFeature = {
    type: "Feature",
    geometry: selectedField.geometry,
    properties: {
      field_id: selectedId,
      source: "usda_csb",
      ...(selectedField.areaAcres ? { area_acres: selectedField.areaAcres } : {}),
    },
  };

  return {
    ...collection,
    available: true,
    truncated: collection.truncated,
    dataset_version: collection.dataset_version ?? selectedField.metadata.dataset_version ?? null,
    features: [...collection.features, selectedFeature],
  };
}

export function FarmMap({
  coordinates,
  selectedField,
  onPointChange,
  onFieldSelect,
  onFieldClear,
}: FarmMapProps) {
  const mapRef = useRef<MapRef>(null);
  const boundaryRequest = useRef<AbortController | null>(null);
  const drawControl = useRef<MaplibreTerradrawControl | null>(null);
  const manualFeatureId = useRef<DrawFeatureId | null>(null);
  const drawingModeRef = useRef<DrawingMode>("idle");
  const selectedFieldRef = useRef(selectedField);
  const coordinatesRef = useRef(coordinates);
  const onFieldSelectRef = useRef(onFieldSelect);
  const onFieldClearRef = useRef(onFieldClear);
  const editSyncFrame = useRef<number | null>(null);
  const suppressCoordinateFly = useRef(false);
  const [basemap, setBasemap] = useState<BasemapMode>(satelliteStyle ? "satellite" : "standard");
  const [fields, setFields] = useState<FieldBoundaryCollectionResponse>(emptyFieldCollection);
  const [boundaryStatus, setBoundaryStatus] = useState<BoundaryStatus>("zoom");
  const [hoveredFieldId, setHoveredFieldId] = useState<string | null>(null);
  const [drawingMode, setDrawingMode] = useState<DrawingMode>("idle");
  const [drawingReady, setDrawingReady] = useState(false);
  const [draftAreaAcres, setDraftAreaAcres] = useState<number | null>(null);
  const [drawError, setDrawError] = useState<string | null>(null);
  const [selectedBoundaryOverlay, setSelectedBoundaryOverlay] =
    useState<BoundaryOverlay | null>(null);

  const selectedFieldId = selectedField?.metadata.source_id ?? "";
  const visibleFields = useMemo(
    () => displayedFieldCollection(fields, selectedField),
    [fields, selectedField],
  );
  const mappedFieldsGeoJson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: visibleFields.features,
    }),
    [visibleFields.features],
  );
  const selectedMappedField = useMemo(
    () =>
      selectedFieldId
        ? visibleFields.features.find(
            (feature) => feature.properties.field_id === selectedFieldId,
          ) ?? null
        : null,
    [selectedFieldId, visibleFields.features],
  );
  const manualBoundarySelected = selectedField?.metadata.source === "farmer_drawn";

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !map.isStyleLoaded()) return;

    const frame = requestAnimationFrame(() => raiseFieldLayers(map));
    return () => cancelAnimationFrame(frame);
  }, [basemap, mappedFieldsGeoJson, selectedMappedField]);

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !selectedMappedField) {
      setSelectedBoundaryOverlay(null);
      return;
    }

    const frame = requestAnimationFrame(() => {
      setSelectedBoundaryOverlay(projectBoundaryOverlay(map, selectedMappedField.geometry));
    });
    return () => cancelAnimationFrame(frame);
  }, [basemap, selectedMappedField]);

  useEffect(() => {
    selectedFieldRef.current = selectedField;
    coordinatesRef.current = coordinates;
    onFieldSelectRef.current = onFieldSelect;
    onFieldClearRef.current = onFieldClear;

    if (selectedField?.metadata.source === "farmer_drawn") return;
    const draw = drawControl.current?.getTerraDrawInstance();
    if (!draw || manualFeatureId.current === null) return;

    draw.clear();
    manualFeatureId.current = null;
    drawingModeRef.current = "idle";
    setDrawingMode("idle");
    setDraftAreaAcres(null);
    setDrawError(null);
  }, [coordinates, onFieldClear, onFieldSelect, selectedField]);

  const coordinateLatitude = coordinates?.latitude;
  const coordinateLongitude = coordinates?.longitude;

  useEffect(() => {
    if (coordinateLatitude === undefined || coordinateLongitude === undefined || !mapRef.current) {
      return;
    }
    if (suppressCoordinateFly.current) {
      suppressCoordinateFly.current = false;
      return;
    }

    const map = mapRef.current.getMap();
    map.flyTo({
      center: [coordinateLongitude, coordinateLatitude],
      zoom: Math.max(map.getZoom(), 12.5),
      duration: 700,
    });
  }, [coordinateLatitude, coordinateLongitude]);

  useEffect(
    () => () => {
      boundaryRequest.current?.abort();
      if (editSyncFrame.current !== null) cancelAnimationFrame(editSyncFrame.current);
      const map = mapRef.current?.getMap();
      const control = drawControl.current;
      if (map && control) {
        try {
          map.removeControl(control);
        } catch {
          // The map can finish its own teardown before this component cleanup runs.
        }
      }
      drawControl.current = null;
    },
    [],
  );

  function setActiveDrawingMode(mode: DrawingMode) {
    drawingModeRef.current = mode;
    setDrawingMode(mode);
  }

  function syncManualFeature(draw: DrawInstance, id: DrawFeatureId, finalizePoint = true) {
    const feature = draw.getSnapshotFeature(id);
    const summary = summarizeFarmBoundary(feature?.geometry);
    if (!summary) {
      setDrawError("The field outline is not a valid closed boundary.");
      return false;
    }

    const { latitude, longitude } = summary.representativePoint;
    if (latitude < 25.8 || latitude > 36.6 || longitude < -106.7 || longitude > -93.4) {
      setDrawError("Draw the field boundary within Texas.");
      return false;
    }

    setDraftAreaAcres(summary.areaAcres);
    setDrawError(null);
    const representativePoint = summary.representativePoint;
    const nextCoordinates = roundedCoordinates(
      representativePoint.latitude,
      representativePoint.longitude,
    );
    const currentPoint = coordinatesRef.current;
    if (
      !finalizePoint &&
      (!currentPoint ||
        currentPoint.latitude !== nextCoordinates.latitude ||
        currentPoint.longitude !== nextCoordinates.longitude)
    ) {
      suppressCoordinateFly.current = true;
    }
    onFieldSelectRef.current(
      {
        geometry: summary.geometry,
        metadata: { source: "farmer_drawn" },
        areaAcres: summary.areaAcres,
      },
      nextCoordinates,
    );
    return true;
  }

  function initializeDrawing(map: MapLibreMap) {
    if (drawControl.current) return;

    const control = new MaplibreTerradrawControl({
      modes: ["polygon", "select"],
      open: false,
      showDeleteConfirmation: false,
      adapterOptions: { prefixId: "cropsage-field" },
    });
    map.addControl(control, "top-left");
    drawControl.current = control;
    control.activate();

    const internalToolbar = map
      .getContainer()
      .querySelector<HTMLElement>(".maplibregl-terradraw-add-control")
      ?.closest<HTMLElement>(".maplibregl-ctrl-group");
    if (internalToolbar) internalToolbar.hidden = true;

    const draw = control.getTerraDrawInstance();
    if (!draw) {
      setDrawError("Field drawing could not be initialized.");
      return;
    }
    draw.setMode("default");
    setDrawingReady(true);

    draw.on("change", (ids) => {
      const candidateId = manualFeatureId.current ?? ids.at(-1);
      if (candidateId === undefined || candidateId === null) return;

      const preview = summarizeFarmBoundary(draw.getSnapshotFeature(candidateId)?.geometry);
      if (preview) setDraftAreaAcres(preview.areaAcres);

      if (drawingModeRef.current !== "edit" || candidateId !== manualFeatureId.current) return;
      if (editSyncFrame.current !== null) cancelAnimationFrame(editSyncFrame.current);
      editSyncFrame.current = requestAnimationFrame(() => {
        editSyncFrame.current = null;
        syncManualFeature(draw, candidateId, false);
      });
    });

    draw.on("finish", (id) => {
      if (drawingModeRef.current !== "draw") {
        if (id === manualFeatureId.current) syncManualFeature(draw, id, false);
        return;
      }

      const supersededIds = draw
        .getSnapshot()
        .filter((feature) => feature.id !== id && feature.properties.mode === "polygon")
        .map((feature) => feature.id)
        .filter((featureId): featureId is DrawFeatureId => featureId !== undefined);
      if (supersededIds.length) draw.removeFeatures(supersededIds);

      manualFeatureId.current = id;
      if (!syncManualFeature(draw, id)) return;
      draw.setMode("select");
      draw.selectFeature(id);
      setActiveDrawingMode("edit");
    });

    const existing = selectedFieldRef.current;
    if (existing?.metadata.source === "farmer_drawn" && existing.geometry.type === "Polygon") {
      const id = "farmer-boundary";
      const validation = draw.addFeatures([
        {
          type: "Feature",
          id,
          properties: { mode: "polygon" },
          geometry: existing.geometry,
        },
      ]);
      if (validation.every((result) => result.valid)) {
        manualFeatureId.current = id;
        setDraftAreaAcres(existing.areaAcres);
      }
    }
  }

  async function loadVisibleFields(map: MapLibreMap) {
    if (map.getZoom() < FIELD_MIN_ZOOM) {
      boundaryRequest.current?.abort();
      setFields(emptyFieldCollection);
      setBoundaryStatus("zoom");
      return;
    }

    const bounds = map.getBounds();
    const west = Math.max(bounds.getWest(), -106.7);
    const south = Math.max(bounds.getSouth(), 25.8);
    const east = Math.min(bounds.getEast(), -93.4);
    const north = Math.min(bounds.getNorth(), 36.6);
    if (west >= east || south >= north) {
      setFields(emptyFieldCollection);
      setBoundaryStatus("unavailable");
      return;
    }
    const bbox = [west, south, east, north]
      .map((coordinate) => coordinate.toFixed(6))
      .join(",");
    const controller = new AbortController();
    boundaryRequest.current?.abort();
    boundaryRequest.current = controller;
    setBoundaryStatus("loading");

    try {
      const response = await fetch(
        `/api/field-boundaries?bbox=${encodeURIComponent(bbox)}&zoom=${map.getZoom().toFixed(2)}`,
        { signal: controller.signal, headers: { accept: "application/json" } },
      );
      const parsed = fieldBoundaryCollectionResponseSchema.safeParse(await response.json());

      if (!response.ok || !parsed.success) throw new Error("Invalid field boundary response");
      setFields(parsed.data);
      setBoundaryStatus(
        parsed.data.features.length
          ? parsed.data.truncated
            ? "truncated"
            : "ready"
          : parsed.data.coverage_status === "covered"
            ? "empty"
            : parsed.data.coverage_status === "partial" ||
                parsed.data.coverage_status === "not_loaded"
              ? "not_loaded"
              : "unavailable",
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setFields(emptyFieldCollection);
      setBoundaryStatus("unavailable");
    }
  }

  function selectMapTarget(event: MapLayerMouseEvent) {
    if (drawingModeRef.current !== "idle") return;

    const fieldId = event.features?.[0]?.properties?.field_id;
    const feature = fieldId
      ? visibleFields.features.find((candidate) => candidate.properties.field_id === fieldId)
      : null;

    if (feature && visibleFields.dataset_version) {
      selectMappedField(feature, event.lngLat.lat, event.lngLat.lng);
      return;
    }

    onPointChange({
      latitude: Number(event.lngLat.lat.toFixed(6)),
      longitude: Number(event.lngLat.lng.toFixed(6)),
    });
  }

  function selectMappedField(
    feature: FieldBoundaryFeature,
    fallbackLatitude?: number,
    fallbackLongitude?: number,
  ) {
    if (!visibleFields.dataset_version) return;

    const draw = drawControl.current?.getTerraDrawInstance();
    if (draw) draw.clear();
    manualFeatureId.current = null;
    setDraftAreaAcres(null);
    setDrawError(null);
    setActiveDrawingMode("idle");

    const latitude = feature.properties.representative_latitude ?? fallbackLatitude;
    const longitude = feature.properties.representative_longitude ?? fallbackLongitude;
    if (latitude === undefined || longitude === undefined) return;

    onFieldSelect(
      {
        geometry: feature.geometry,
        metadata: {
          source: "usda_csb",
          source_id: feature.properties.field_id,
          dataset_version: visibleFields.dataset_version,
        },
        areaAcres: feature.properties.area_acres ?? null,
      },
      roundedCoordinates(latitude, longitude),
    );
  }

  function switchBasemap(mode: BasemapMode) {
    if (mode === basemap) return;
    const map = mapRef.current?.getMap();
    const control = drawControl.current;
    if (map && control) {
      map.removeControl(control);
      drawControl.current = null;
      setDrawingReady(false);
    }
    setBasemap(mode);
  }

  function trackHoveredField(event: MapLayerMouseEvent) {
    if (drawingModeRef.current !== "idle") {
      setHoveredFieldId(null);
      return;
    }
    setHoveredFieldId(event.features?.[0]?.properties?.field_id ?? null);
  }

  function beginDrawing() {
    const control = drawControl.current;
    if (!control) {
      setDrawError("Field drawing is still loading.");
      return;
    }
    control.activate();
    const draw = control.getTerraDrawInstance();
    if (!draw) {
      setDrawError("Field drawing could not be initialized.");
      return;
    }

    if (drawingModeRef.current === "draw") {
      draw.clear();
      manualFeatureId.current = null;
      setDraftAreaAcres(null);
      setDrawError(null);
      setActiveDrawingMode("idle");
      draw.setMode("default");
      return;
    }

    draw.clear();
    manualFeatureId.current = null;
    onFieldClearRef.current();
    setHoveredFieldId(null);
    setDraftAreaAcres(null);
    setDrawError(null);
    setActiveDrawingMode("draw");
    draw.setMode("polygon");
  }

  function toggleEditing() {
    const draw = drawControl.current?.getTerraDrawInstance();
    const id = manualFeatureId.current;
    if (!draw || id === null) return;

    if (drawingModeRef.current === "edit") {
      syncManualFeature(draw, id);
      draw.setMode("default");
      setActiveDrawingMode("idle");
      return;
    }

    draw.setMode("select");
    draw.selectFeature(id);
    setDrawError(null);
    setActiveDrawingMode("edit");
  }

  function clearManualBoundary() {
    const draw = drawControl.current?.getTerraDrawInstance();
    if (draw) {
      draw.clear();
      draw.setMode("default");
    }
    manualFeatureId.current = null;
    setDraftAreaAcres(null);
    setDrawError(null);
    setActiveDrawingMode("idle");
    onFieldClearRef.current();
  }

  function clearSelectedField() {
    if (selectedFieldRef.current?.metadata.source === "farmer_drawn") {
      clearManualBoundary();
      return;
    }
    onFieldClearRef.current();
  }

  const instruction = drawError
    ? drawError
    : drawingMode === "draw"
      ? "Select each field corner; select the first point to close"
      : drawingMode === "edit"
        ? "Drag the boundary points to adjust the field"
        : boundaryMessage(boundaryStatus, Boolean(selectedField));

  return (
    <div className="farm-map" aria-label="Texas farm location map">
      <MapView
        ref={mapRef}
        initialViewState={{ latitude: 31.1, longitude: -99.4, zoom: 4.7 }}
        mapStyle={basemap === "satellite" && satelliteStyle ? satelliteStyle : standardStyle}
        maxBounds={[-107.5, 24.5, -92.5, 37.5]}
        minZoom={4}
        maxZoom={19}
        onClick={selectMapTarget}
        onLoad={(event) => {
          initializeDrawing(event.target);
          void loadVisibleFields(event.target);
          requestAnimationFrame(() => raiseFieldLayers(event.target));
        }}
        onIdle={(event) => {
          if (!drawControl.current) initializeDrawing(event.target);
          raiseFieldLayers(event.target);
        }}
        onMoveEnd={(event) => void loadVisibleFields(event.target)}
        onMove={(event) => {
          if (selectedMappedField) {
            setSelectedBoundaryOverlay(
              projectBoundaryOverlay(event.target, selectedMappedField.geometry),
            );
          }
        }}
        onResize={(event) => {
          if (selectedMappedField) {
            setSelectedBoundaryOverlay(
              projectBoundaryOverlay(event.target, selectedMappedField.geometry),
            );
          }
        }}
        onMouseMove={trackHoveredField}
        onMouseLeave={() => setHoveredFieldId(null)}
        interactiveLayerIds={visibleFields.features.length ? [FIELD_FILL_LAYER_ID] : []}
        cursor={drawingMode === "draw" ? "crosshair" : hoveredFieldId ? "pointer" : "crosshair"}
        attributionControl={{ compact: true }}
      >
        <Source id="mapped-fields" type="geojson" data={mappedFieldsGeoJson}>
          <Layer
            id={FIELD_FILL_LAYER_ID}
            type="fill"
            paint={{
              "fill-color": "#b9d6c7",
              "fill-opacity": [
                "case",
                ["==", ["get", "field_id"], hoveredFieldId ?? ""],
                0.48,
                0.32,
              ],
            }}
          />
          <Layer
            id={FIELD_OUTLINE_LAYER_ID}
            type="line"
            paint={{
              "line-color": "#176b4f",
              "line-opacity": 0.95,
              "line-width": [
                "case",
                ["==", ["get", "field_id"], hoveredFieldId ?? ""],
                2.5,
                1.6,
              ],
            }}
          />
        </Source>

        {selectedMappedField ? (
          <Source id="selected-mapped-field" type="geojson" data={selectedMappedField}>
            <Layer
              id={SELECTED_FIELD_FILL_LAYER_ID}
              type="fill"
              paint={{
                "fill-color": "#14945f",
                "fill-opacity": 0.68,
              }}
            />
            <Layer
              id={SELECTED_FIELD_OUTLINE_LAYER_ID}
              type="line"
              paint={{
                "line-color": "#005f39",
                "line-opacity": 1,
                "line-width": 4,
              }}
            />
          </Source>
        ) : null}

        <NavigationControl position="top-right" showCompass={false} />
        {visibleFields.features.map((feature) =>
          feature.properties.area_acres &&
          feature.properties.representative_latitude !== undefined &&
          feature.properties.representative_longitude !== undefined ? (
            <Marker
              key={feature.properties.field_id}
              latitude={feature.properties.representative_latitude}
              longitude={feature.properties.representative_longitude}
              anchor="center"
            >
              <button
                type="button"
                className={`field-area-marker${feature.properties.field_id === selectedFieldId ? " selected" : ""}`}
                onClick={(event) => {
                  event.stopPropagation();
                  selectMappedField(feature);
                }}
                aria-label={`Select ${feature.properties.area_acres.toLocaleString(undefined, { maximumFractionDigits: 1 })} acre mapped field`}
              >
                {feature.properties.field_id === selectedFieldId ? "Selected · " : ""}
                {feature.properties.area_acres.toLocaleString(undefined, {
                  maximumFractionDigits: 1,
                })}{" "}
                ac
              </button>
            </Marker>
          ) : null,
        )}
        {coordinates ? (
          <Marker latitude={coordinates.latitude} longitude={coordinates.longitude} anchor="bottom">
            <span className="selected-map-pin" aria-label="Selected farm point">
              <MapPin aria-hidden="true" size={22} />
            </span>
          </Marker>
        ) : null}
      </MapView>

      {selectedBoundaryOverlay ? (
        <svg
          className="selected-field-boundary-overlay"
          viewBox={`0 0 ${selectedBoundaryOverlay.width} ${selectedBoundaryOverlay.height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d={selectedBoundaryOverlay.path} fillRule="evenodd" />
        </svg>
      ) : null}

      <div className={`map-instruction${drawError ? " error" : ""}`} role="status">
        {instruction}
      </div>

      <div className="map-drawing-control" aria-label="Field boundary tools">
        <button
          type="button"
          className={drawingMode === "draw" ? "selected" : ""}
          aria-pressed={drawingMode === "draw"}
          onClick={beginDrawing}
          disabled={!drawingReady}
          aria-label={drawingMode === "draw" ? "Cancel field drawing" : "Draw field boundary"}
          title={drawingMode === "draw" ? "Cancel drawing" : "Draw field boundary"}
        >
          {drawingMode === "draw" ? <X size={18} aria-hidden="true" /> : <PenTool size={18} aria-hidden="true" />}
        </button>
        <button
          type="button"
          className={drawingMode === "edit" ? "selected" : ""}
          aria-pressed={drawingMode === "edit"}
          disabled={!manualBoundarySelected || drawingMode === "draw"}
          onClick={toggleEditing}
          aria-label={drawingMode === "edit" ? "Finish editing field boundary" : "Edit field boundary"}
          title={drawingMode === "edit" ? "Finish editing" : "Edit field boundary"}
        >
          {drawingMode === "edit" ? <Check size={18} aria-hidden="true" /> : <Pencil size={18} aria-hidden="true" />}
        </button>
        <button
          type="button"
          disabled={!manualBoundarySelected}
          onClick={clearManualBoundary}
          aria-label="Delete field boundary"
          title="Delete field boundary"
        >
          <Trash2 size={18} aria-hidden="true" />
        </button>
      </div>

      {satelliteStyle ? (
        <div className="map-mode-control" aria-label="Map appearance">
          <button
            type="button"
            className={basemap === "standard" ? "selected" : ""}
            aria-pressed={basemap === "standard"}
            onClick={() => switchBasemap("standard")}
          >
            <MapIcon size={15} aria-hidden="true" /> Map
          </button>
          <button
            type="button"
            className={basemap === "satellite" ? "selected" : ""}
            aria-pressed={basemap === "satellite"}
            onClick={() => switchBasemap("satellite")}
          >
            <Satellite size={15} aria-hidden="true" /> Satellite
          </button>
        </div>
      ) : null}

      {drawingMode === "draw" && draftAreaAcres ? (
        <div className="drawing-area-readout" aria-live="polite">
          {draftAreaAcres.toLocaleString(undefined, { maximumFractionDigits: 1 })} ac
        </div>
      ) : null}

      {selectedField ? (
        <div className="selected-field-chip">
          <Check size={16} aria-hidden="true" />
          <span>
            {selectedField.areaAcres
              ? `${selectedField.areaAcres.toLocaleString(undefined, { maximumFractionDigits: 1 })} ac`
              : selectedField.metadata.source === "farmer_drawn"
                ? "Drawn field"
                : "Mapped field"}
          </span>
          <button type="button" onClick={clearSelectedField} aria-label="Clear selected field" title="Clear selected field">
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

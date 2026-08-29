"use client";

import { MapPin } from "lucide-react";
import type { StyleSpecification } from "maplibre-gl";
import Map, { Marker, NavigationControl, type MapLayerMouseEvent } from "react-map-gl/maplibre";

type Coordinates = {
  latitude: number;
  longitude: number;
};

type FarmMapProps = {
  coordinates: Coordinates | null;
  onChange: (coordinates: Coordinates) => void;
};

const osmStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export function FarmMap({ coordinates, onChange }: FarmMapProps) {
  function selectPoint(event: MapLayerMouseEvent) {
    onChange({
      latitude: Number(event.lngLat.lat.toFixed(6)),
      longitude: Number(event.lngLat.lng.toFixed(6)),
    });
  }

  return (
    <div className="farm-map" aria-label="Texas farm location map">
      <Map
        initialViewState={{ latitude: 31.1, longitude: -99.4, zoom: 4.7 }}
        mapStyle={osmStyle}
        maxBounds={[-107.5, 24.5, -92.5, 37.5]}
        minZoom={4}
        onClick={selectPoint}
        cursor="crosshair"
        attributionControl={{ compact: true }}
      >
        <NavigationControl position="top-right" showCompass={false} />
        {coordinates ? (
          <Marker latitude={coordinates.latitude} longitude={coordinates.longitude} anchor="bottom">
            <span className="selected-map-pin" aria-label="Selected farm point">
              <MapPin aria-hidden="true" size={24} />
            </span>
          </Marker>
        ) : null}
      </Map>
      <div className="map-instruction">Click the map to place the farm point</div>
    </div>
  );
}

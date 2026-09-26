#!/usr/bin/env python3
"""
AapdaNetra-X — Phase 6.2 Offline OSM Graph Downloader
Downloads OpenStreetMap drivable road network for approved Delhi study area
and caches it locally as GraphML for zero-latency runtime routing.

CRITICAL ARCHITECTURAL REQUIREMENT:
This script is executed out-of-band during setup / initialization.
NEVER call OSMnx network functions during runtime HTTP API requests (/api/routes).
"""
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import osmnx as ox

DEFAULT_BBOX = (77.1900, 28.6100, 77.2600, 28.6700)  # (west, south, east, north)
CACHE_DIR = ROOT_DIR / "backend" / "app" / "data" / "osm_cache"
OUTPUT_FILE = CACHE_DIR / "delhi_sector_b.graphml"


def download_and_cache_osm_graph(
    bbox: tuple = DEFAULT_BBOX,
    output_path: Path = OUTPUT_FILE
) -> bool:
    """
    Downloads OSM drivable road network for the specified bounding box
    and saves it to local GraphML file.
    """
    print(f"=== AapdaNetra-X Phase 6.2 OSM Downloader ===")
    print(f"Target Bounding Box (W, S, E, N): {bbox}")
    print(f"Output File Path: {output_path}")

    os.makedirs(output_path.parent, exist_ok=True)

    try:
        print("Fetching drivable road network from OpenStreetMap (Overpass API)...")
        # In OSMnx 2.x, bbox parameter is tuple (left/west, bottom/south, right/east, top/north)
        G = ox.graph_from_bbox(bbox=bbox, network_type="drive", simplify=True)

        node_count = G.number_of_nodes()
        edge_count = G.number_of_edges()
        print(f"Successfully downloaded graph: {node_count} nodes, {edge_count} edges")

        print("Saving graph to GraphML format...")
        ox.save_graphml(G, filepath=output_path)

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✅ Saved GraphML to {output_path} ({file_size_mb:.2f} MB)")
        return True

    except Exception as e:
        print(f"❌ Error downloading OSM graph: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    success = download_and_cache_osm_graph()
    sys.exit(0 if success else 1)

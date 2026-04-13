# geometry.py
"""
Geometry, projection, GeoJSON loading, and adjacency graph for GPD.
Pure functions with no side effects (except file I/O for loading).
"""

import json
import math
import logging

from constants import (
    MAX_MERCATOR_LAT,
    ADJACENCY_TOUCH_THRESHOLD,
    ADJACENCY_NEIGHBOR_RADIUS,
    ADJACENCY_CLOSE_COST,
    ADJACENCY_FAR_COST,
    ADJACENCY_FAR_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ============================================================
# Mercator projection
# ============================================================


def mercator_x(lon_deg, map_w):
    """Convert longitude to pixel x coordinate."""
    return (lon_deg + 180.0) / 360.0 * map_w


def mercator_y(lat_deg, map_h):
    """Convert latitude to pixel y coordinate using Mercator projection."""
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat_deg))
    lat_rad = math.radians(lat)
    merc_n = math.log(math.tan(math.pi / 4 + lat_rad / 2))
    y = (1 - merc_n / math.pi) / 2
    return y * map_h


def lonlat_to_pixel(lon, lat, map_w, map_h):
    """Convert (lon, lat) to integer pixel coordinates."""
    return int(round(mercator_x(lon, map_w))), int(round(mercator_y(lat, map_h)))


# ============================================================
# Polygon math
# ============================================================


def polygon_bbox(poly):
    """Return (min_x, min_y, max_x, max_y) bounding box of a polygon."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_poly(x, y, poly):
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def polygon_centroid(poly):
    """Compute the centroid of a polygon using the shoelace formula."""
    n = len(poly)
    if n == 0:
        return (0, 0)
    area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a = x0 * y1 - x1 * y0
        area += a
        cx += (x0 + x1) * a
        cy += (y0 + y1) * a
    if abs(area) < 1e-6:
        return (sum(p[0] for p in poly) // n, sum(p[1] for p in poly) // n)
    area = area / 2.0
    cx = cx / (6.0 * area)
    cy = cy / (6.0 * area)
    return (int(round(cx)), int(round(cy)))


def polygon_area(poly):
    """Compute signed area of a polygon using the shoelace formula."""
    a = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


# ============================================================
# GeoJSON loader
# ============================================================


def load_countries_from_geojson(path, map_w, map_h):
    """
    Load countries from a GeoJSON file and return a dict of {cid: country_dict}.

    Each country_dict has keys:
        id, name, continent, polygons, centroid, bbox, owner, troops, adj
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load GeoJSON from %s: %s", path, e)
        return {}

    features = data.get("features", [])
    countries = {}
    cid = 1

    for feat in features:
        props = feat.get("properties", {})
        name = (
            props.get("ADMIN")
            or props.get("name")
            or props.get("NAME")
            or f"Country {cid}"
        )
        cont = (
            props.get("REGION_UN")
            or props.get("continent")
            or props.get("region")
            or ""
        )
        geom = feat.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        polygons_world = []
        if gtype == "Polygon":
            for ring in coords:
                pts = [lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                polygons_world.append(pts)
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    pts = [lonlat_to_pixel(lon, lat, map_w, map_h) for lon, lat in ring]
                    polygons_world.append(pts)
        else:
            cid += 1
            continue

        if not polygons_world:
            cid += 1
            continue

        largest = max(polygons_world, key=lambda r: abs(polygon_area(r)) if r else 0)
        centroid = polygon_centroid(largest) if largest else (0, 0)

        bbox = None
        if polygons_world:
            xs = [p[0] for ring in polygons_world for p in ring]
            ys = [p[1] for ring in polygons_world for p in ring]
            bbox = (min(xs), min(ys), max(xs), max(ys))

        countries[cid] = {
            "id": cid,
            "name": name,
            "continent": cont,
            "polygons": polygons_world,
            "centroid": centroid,
            "bbox": bbox,
            "owner": None,
            "troops": 0,
            "adj": [],
        }
        cid += 1

    logger.info("Loaded %d countries from GeoJSON", len(countries))
    return countries


def build_adjacency(countries, touch_threshold=None, neigh_radius=None):
    """
    Build the adjacency graph between countries based on bounding box
    overlap and centroid distance.
    """
    if touch_threshold is None:
        touch_threshold = ADJACENCY_TOUCH_THRESHOLD
    if neigh_radius is None:
        neigh_radius = ADJACENCY_NEIGHBOR_RADIUS

    ids = list(countries.keys())
    for i in range(len(ids)):
        a = countries[ids[i]]
        ax0, ay0, ax1, ay1 = a["bbox"] if a["bbox"] else (0, 0, 0, 0)
        for j in range(i + 1, len(ids)):
            b = countries[ids[j]]
            bx0, by0, bx1, by1 = b["bbox"] if b["bbox"] else (0, 0, 0, 0)
            overlap = not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)

            cen_a = a["centroid"]
            cen_b = b["centroid"]
            if cen_a and cen_b:
                dx = cen_a[0] - cen_b[0]
                dy = cen_a[1] - cen_b[1]
                d = math.hypot(dx, dy)
            else:
                d = 9999

            if overlap or d <= neigh_radius:
                cost = (
                    0
                    if overlap
                    else ADJACENCY_CLOSE_COST
                    if d < ADJACENCY_FAR_THRESHOLD
                    else ADJACENCY_FAR_COST
                )
                a["adj"].append({"to": b["id"], "cost": cost})
                b["adj"].append({"to": a["id"], "cost": cost})

    logger.debug("Built adjacency graph for %d countries", len(countries))

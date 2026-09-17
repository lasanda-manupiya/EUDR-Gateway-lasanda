"""
Server-side validation and normalisation of source-plot geometry.
The browser map is a convenience; this module is authoritative.
"""
import json

from django.conf import settings
from django.contrib.gis.geos import GEOSException, GEOSGeometry, MultiPolygon, Point, Polygon

MAX_VERTICES = 100_000
EQUAL_AREA_SRID = 6933  # WGS 84 / NSIDC EASE-Grid 2.0 Global (equal area)


class GeometryError(ValueError):
    pass


def _check_position(pos, where):
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        raise GeometryError(f"{where}: each coordinate must be [longitude, latitude].")
    lon, lat = pos[0], pos[1]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lon, lat)):
        raise GeometryError(f"{where}: coordinates must be numbers.")
    if not (-180 <= lon <= 180):
        raise GeometryError(f"{where}: longitude {lon} is outside -180 to 180. "
                            "GeoJSON uses [longitude, latitude] order — check they are not swapped.")
    if not (-90 <= lat <= 90):
        raise GeometryError(f"{where}: latitude {lat} is outside -90 to 90. "
                            "GeoJSON uses [longitude, latitude] order — check they are not swapped.")
    return [float(lon), float(lat)]


def _polygon(coords, where):
    if not isinstance(coords, list) or not coords:
        raise GeometryError(f"{where}: polygon has no rings.")
    rings = []
    for i, ring in enumerate(coords):
        if not isinstance(ring, list):
            raise GeometryError(f"{where}: ring {i + 1} is not a list of coordinates.")
        pts = [_check_position(p, where) for p in ring]
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])  # close the ring for the user
        if len(pts) < 4:
            raise GeometryError(f"{where}: a polygon needs at least 3 distinct corner points.")
        rings.append(pts)
    try:
        poly = Polygon(*rings, srid=4326)
    except (GEOSException, ValueError, TypeError) as exc:
        raise GeometryError(f"{where}: could not build polygon ({exc}).")
    if not poly.valid:
        raise GeometryError(f"{where}: the polygon is not valid ({poly.valid_reason}). "
                            "This usually means edges cross each other. Redraw the outline without crossing lines.")
    if poly.area == 0:
        raise GeometryError(f"{where}: the polygon has zero area.")
    return poly


def parse_geojson(text):
    """
    Accepts Polygon, MultiPolygon, Point, Feature, FeatureCollection or GeometryCollection.
    Returns dict(geometry=MultiPolygon|None, point=Point|None, area_ha=float|None).
    """
    if not text or not text.strip():
        raise GeometryError("No location provided. Draw the area on the map, upload a GeoJSON file or enter coordinates.")
    if len(text.encode()) > settings.GEOJSON_MAX_BYTES:
        raise GeometryError("The GeoJSON is too large.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeometryError(f"This is not valid GeoJSON/JSON (line {exc.lineno}, column {exc.colno}).")

    polygons, points = [], []

    def walk(node, where):
        if not isinstance(node, dict) or "type" not in node:
            raise GeometryError(f"{where}: missing GeoJSON 'type'.")
        t = node["type"]
        if t == "FeatureCollection":
            feats = node.get("features")
            if not isinstance(feats, list) or not feats:
                raise GeometryError("The FeatureCollection contains no features.")
            for i, f in enumerate(feats):
                walk(f, f"Feature {i + 1}")
        elif t == "Feature":
            if node.get("geometry") is None:
                raise GeometryError(f"{where}: feature has no geometry.")
            walk(node["geometry"], where)
        elif t == "GeometryCollection":
            for i, g in enumerate(node.get("geometries") or []):
                walk(g, f"{where} geometry {i + 1}")
        elif t == "Polygon":
            polygons.append(_polygon(node.get("coordinates"), where))
        elif t == "MultiPolygon":
            for i, c in enumerate(node.get("coordinates") or []):
                polygons.append(_polygon(c, f"{where} part {i + 1}"))
        elif t == "Point":
            lon, lat = _check_position(node.get("coordinates"), where)
            points.append(Point(lon, lat, srid=4326))
        else:
            raise GeometryError(f"{where}: geometry type '{t}' is not supported. Use Polygon, MultiPolygon or Point.")

    walk(data, "Geometry")

    if sum(p.num_coords for p in polygons) > MAX_VERTICES:
        raise GeometryError(f"The geometry has more than {MAX_VERTICES:,} points. Simplify it before uploading.")
    if polygons and points:
        raise GeometryError("Provide either polygons or a single point for one source, not both.")
    if len(points) > 1:
        raise GeometryError("Only one point is allowed per source. Register each point location as a separate source.")

    if polygons:
        multi = MultiPolygon(*polygons, srid=4326)
        if not multi.valid:
            raise GeometryError("The polygons overlap each other. Merge overlapping areas or remove duplicates.")
        return {"geometry": multi, "point": None, "area_ha": area_hectares(multi)}
    if points:
        return {"geometry": None, "point": points[0], "area_ha": None}
    raise GeometryError("No usable geometry was found.")


def area_hectares(geom):
    return geom.transform(EQUAL_AREA_SRID, clone=True).area / 10_000


def to_feature_collection(plot):
    geom = plot.geometry or plot.point
    if geom is None:
        return None
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": json.loads(geom.geojson),
        "properties": {"id": plot.pk, "name": plot.name, "plot_reference": plot.plot_reference,
                       "country": plot.country, "area_ha": float(plot.area_ha) if plot.area_ha is not None else None},
    }]}

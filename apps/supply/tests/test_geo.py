import json
from django.test import SimpleTestCase
from apps.supply.geo import GeometryError, parse_geojson

SQ = [[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]


class GeoJSONValidationTest(SimpleTestCase):
    def ok(self, obj):
        return parse_geojson(json.dumps(obj))

    def bad(self, obj_or_text, fragment):
        text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
        with self.assertRaises(GeometryError) as cm:
            parse_geojson(text)
        self.assertIn(fragment, str(cm.exception))

    def test_polygon_area_and_type(self):
        r = self.ok({"type": "Polygon", "coordinates": [SQ]})
        self.assertEqual(r["geometry"].geom_type, "MultiPolygon")
        self.assertAlmostEqual(r["area_ha"], 123.1, delta=0.5)

    def test_multipolygon_and_featurecollection(self):
        sq2 = [[x + 1, y] for x, y in SQ]
        r = self.ok({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[SQ], [sq2]]}, "properties": {}}]})
        self.assertEqual(len(r["geometry"]), 2)

    def test_polygon_with_hole(self):
        hole = [[0.004, 0.004], [0.006, 0.004], [0.006, 0.006], [0.004, 0.006], [0.004, 0.004]]
        r = self.ok({"type": "Polygon", "coordinates": [SQ, hole]})
        self.assertLess(r["area_ha"], 123.1)

    def test_unclosed_ring_is_closed(self):
        self.ok({"type": "Polygon", "coordinates": [SQ[:-1]]})

    def test_point(self):
        r = self.ok({"type": "Point", "coordinates": [6.95, 50.93]})
        self.assertIsNone(r["geometry"])
        self.assertEqual(r["point"].coords, (6.95, 50.93))

    def test_rejections(self):
        self.bad("not json", "not valid")
        self.bad("", "No location")
        self.bad({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "not supported")
        self.bad({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}, "at least 3")
        self.bad({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}, "not valid")
        self.bad({"type": "Point", "coordinates": [50.93, 200]}, "latitude")
        self.bad({"type": "Point", "coordinates": [181, 5]}, "longitude")
        self.bad({"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [1, 1]},
                                                              {"type": "Polygon", "coordinates": [SQ]}]}, "not both")
        self.bad({"type": "MultiPolygon", "coordinates": [[SQ], [SQ]]}, "overlap")
        self.bad({"type": "FeatureCollection", "features": []}, "no features")
        self.bad({"type": "Point", "coordinates": ["a", 1]}, "numbers")

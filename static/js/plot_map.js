/* Source-location map: draw / edit / delete polygons, upload or paste GeoJSON,
   place a point, view coordinates and approximate area.
   The server re-validates everything and computes the authoritative area. */
(function () {
  "use strict";
  var el = document.getElementById("plot-map");
  if (!el || typeof L === "undefined") return;

  var editable = el.dataset.editable === "1";
  var input = document.getElementById("id_geometry_geojson");
  var originInput = document.getElementById("geometry-origin");
  var errorBox = document.getElementById("map-error");
  var summary = document.getElementById("geom-summary");
  var coordsBox = document.getElementById("geom-coords");

  var initial = null;
  var initEl = document.getElementById("plot-initial");
  if (initEl) {
    try {
      initial = JSON.parse(initEl.textContent);
      if (typeof initial === "string") initial = initial ? JSON.parse(initial) : null;
    } catch (e) { initial = null; }
  }

  var street = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
  });
  var imagery = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics"
  });
  var map = L.map(el, { layers: [street], worldCopyJump: true }).setView([20, 0], 2);
  var plotLayer = new L.FeatureGroup().addTo(map);
  var plotStyle = { color: "#12463a", weight: 2.5, fillColor: "#3f8f6b", fillOpacity: 0.28 };

  // Overlays registry: later stages add screening layers here; the plot layer stays on top.
  L.control.layers({ "Street map": street, "Satellite imagery": imagery }, { "Supplier plot": plotLayer },
    { collapsed: false }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  function showError(msg) {
    if (!errorBox) { if (msg) alert(msg); return; }
    errorBox.textContent = msg || "";
    errorBox.hidden = !msg;
  }

  function ringArea(latlngs) { return L.GeometryUtil.geodesicArea(latlngs); }

  function polygonArea(layer) {
    var rings = layer.getLatLngs();
    if (!rings.length) return 0;
    var area = ringArea(rings[0]);
    for (var i = 1; i < rings.length; i++) area -= ringArea(rings[i]);
    return area;
  }

  function addPolygonCoords(coords) {
    // coords: GeoJSON polygon coordinates [[ [lon,lat], ... ], hole, ...]
    var rings = coords.map(function (ring) {
      var r = ring.map(function (p) { return [p[1], p[0]]; });
      if (r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]) r.pop();
      return r;
    });
    plotLayer.addLayer(L.polygon(rings, plotStyle));
  }

  function addGeometry(g) {
    if (!g || !g.type) throw new Error("Missing geometry type.");
    switch (g.type) {
      case "FeatureCollection": (g.features || []).forEach(addGeometry); break;
      case "Feature": addGeometry(g.geometry); break;
      case "GeometryCollection": (g.geometries || []).forEach(addGeometry); break;
      case "Polygon": addPolygonCoords(g.coordinates); break;
      case "MultiPolygon": g.coordinates.forEach(addPolygonCoords); break;
      case "Point": plotLayer.addLayer(L.marker([g.coordinates[1], g.coordinates[0]])); break;
      default: throw new Error("Geometry type " + g.type + " is not supported. Use Polygon, MultiPolygon or Point.");
    }
  }

  function fit() {
    var layers = plotLayer.getLayers();
    if (!layers.length) return;
    if (layers.length === 1 && layers[0] instanceof L.Marker) map.setView(layers[0].getLatLng(), 15);
    else map.fitBounds(plotLayer.getBounds(), { padding: [30, 30], maxZoom: 17 });
  }

  function fmt(n, d) { return Number(n).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }); }

  function render() {
    var layers = plotLayer.getLayers();
    var polys = layers.filter(function (l) { return l instanceof L.Polygon; });
    var points = layers.filter(function (l) { return l instanceof L.Marker; });
    if (!summary) return;
    if (!layers.length) {
      summary.innerHTML = '<p class="muted">Nothing drawn yet.</p>';
      if (coordsBox) coordsBox.innerHTML = "";
      return;
    }
    var html = "<dl>";
    if (polys.length) {
      var total = polys.reduce(function (s, l) { return s + polygonArea(l); }, 0);
      html += "<dt>Polygons</dt><dd>" + polys.length + "</dd>";
      if (!editable && el.dataset.areaHa) html += "<dt>Area</dt><dd>" + fmt(parseFloat(el.dataset.areaHa), 2) + " ha</dd>";
      else html += "<dt>Approximate area</dt><dd>" + fmt(total / 10000, 2) + " ha</dd>";
    }
    if (points.length) html += "<dt>Points</dt><dd>" + points.length + "</dd>";
    html += "</dl>";
    if (polys.length && points.length) html += '<p class="error">Use either polygons or a single point, not both.</p>';
    if (points.length > 1) html += '<p class="error">Only one point per source location.</p>';
    if (editable && polys.length) html += '<p class="help">Final area is calculated precisely when you save.</p>';
    if (points.length === 1 && !polys.length) html += '<p class="help">A point is only suitable for plots of 4 hectares or less.</p>';
    summary.innerHTML = html;

    if (coordsBox) {
      var out = [], shown = 0, MAX = 300;
      polys.forEach(function (l, i) {
        l.getLatLngs().forEach(function (ring, r) {
          out.push("<p class='small'><strong>Polygon " + (i + 1) + (r ? " – hole " + r : "") + "</strong></p><table class='coords'><thead><tr><th>#</th><th>Latitude</th><th>Longitude</th></tr></thead><tbody>");
          ring.forEach(function (ll, k) {
            if (shown++ < MAX) out.push("<tr><td>" + (k + 1) + "</td><td>" + ll.lat.toFixed(6) + "</td><td>" + ll.lng.toFixed(6) + "</td></tr>");
          });
          out.push("</tbody></table>");
        });
      });
      points.forEach(function (m) {
        var ll = m.getLatLng();
        out.push("<p class='small'><strong>Point</strong> " + ll.lat.toFixed(6) + ", " + ll.lng.toFixed(6) + "</p>");
      });
      if (shown > MAX) out.push("<p class='small muted'>Showing first " + MAX + " of " + shown + " vertices.</p>");
      coordsBox.innerHTML = out.join("");
    }
  }

  function sync(origin) {
    render();
    if (!input) return;
    var features = plotLayer.getLayers().map(function (l) { return l.toGeoJSON(); });
    input.value = features.length ? JSON.stringify({ type: "FeatureCollection", features: features }) : "";
    if (origin && originInput) originInput.value = origin;
  }

  function loadText(text, origin) {
    showError("");
    var data;
    try { data = JSON.parse(text); } catch (e) { showError("That is not valid GeoJSON. Check the file or pasted text."); return; }
    var backup = plotLayer.getLayers();
    plotLayer.clearLayers();
    try { addGeometry(data); }
    catch (e) { plotLayer.clearLayers(); backup.forEach(function (l) { plotLayer.addLayer(l); }); showError(e.message); return; }
    fit(); sync(origin);
  }

  if (initial) {
    try { addGeometry(initial); fit(); } catch (e) { showError("The saved location could not be displayed: " + e.message); }
  }
  render();

  if (!editable) return;

  map.addControl(new L.Control.Draw({
    position: "topleft",
    edit: { featureGroup: plotLayer, poly: { allowIntersection: false } },
    draw: {
      polygon: { allowIntersection: false, showArea: false, shapeOptions: plotStyle,
                 drawError: { color: "#a1321f", message: "Edges cannot cross." } },
      rectangle: { shapeOptions: plotStyle, showArea: false },
      marker: true, polyline: false, circle: false, circlemarker: false
    }
  }));

  map.on(L.Draw.Event.CREATED, function (e) {
    var layer = e.layer;
    if (layer instanceof L.Polygon) layer.setStyle(plotStyle);
    plotLayer.addLayer(layer);
    sync(layer instanceof L.Marker ? "coordinates" : "drawn");
  });
  map.on(L.Draw.Event.EDITED, function () { sync("drawn"); });
  map.on(L.Draw.Event.DELETED, function () { sync("drawn"); });

  var fileInput = document.getElementById("geojson-file");
  if (fileInput) fileInput.addEventListener("change", function () {
    var file = fileInput.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { showError("The file is larger than 5 MB. Simplify it first."); return; }
    var reader = new FileReader();
    reader.onload = function () { loadText(reader.result, "uploaded"); };
    reader.onerror = function () { showError("The file could not be read."); };
    reader.readAsText(file);
  });

  var pasteBtn = document.getElementById("load-pasted");
  if (pasteBtn) pasteBtn.addEventListener("click", function () {
    loadText(document.getElementById("geojson-paste").value, "uploaded");
  });

  var pointBtn = document.getElementById("place-point");
  if (pointBtn) pointBtn.addEventListener("click", function () {
    var lat = parseFloat(document.getElementById("point-lat").value);
    var lng = parseFloat(document.getElementById("point-lng").value);
    if (isNaN(lat) || isNaN(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      showError("Enter a latitude between -90 and 90 and a longitude between -180 and 180.");
      return;
    }
    showError("");
    plotLayer.clearLayers();
    plotLayer.addLayer(L.marker([lat, lng]));
    fit(); sync("coordinates");
  });

  // Make the map a resilient size when shown after layout changes.
  setTimeout(function () { map.invalidateSize(); }, 200);
})();

# Browser journey for Stage 1. Needs: dev server on :8000, a fresh DB with
# create_sz_admin --email admin@sustainzone.example --password Correct-Horse-Battery-9, and `playwright install chromium`.
import re, json
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:8000"
PW = "Correct-Horse-Battery-9"
S = "./e2e-screenshots/"
log = []

def mail_link(pattern):
    txt = open("/tmp/server.log").read()
    return re.findall(r"(http://127\.0\.0\.1:8000/" + pattern + r"/\S+/)", txt)[-1]

def diag(pg, tag):
    pg.screenshot(path=S + "FAIL_" + tag + ".png", full_page=True)
    print("FAIL at", tag, pg.url, [e.inner_text() for e in pg.query_selector_all(".error,.msg")])

import os; os.makedirs(S, exist_ok=True)
with sync_playwright() as p:
    br = p.chromium.launch(args=["--no-sandbox"])
    def ctx():
        c = br.new_context(viewport={"width": 1400, "height": 950})
        pg = c.new_page()
        pg.on("console", lambda m: log.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") and "403" not in m.text else None)
        pg.on("pageerror", lambda e: log.append(f"PAGEERROR {e}"))
        return c, pg
    def login(pg, email):
        pg.goto(B + "/accounts/login/"); pg.fill("#id_username", email); pg.fill("#id_password", PW); pg.click("main button[type=submit]")
        pg.wait_for_url(B + "/")

    # SZ admin: create client + entity + invite supplier
    c, pg = ctx(); login(pg, "admin@sustainzone.example")
    pg.goto(B + "/clients/new/")
    for k, v in {"name": "Tsunami Axis", "address": "Hafenstrasse 1, Hamburg", "main_contact_name": "Jonas Weber",
                 "main_contact_email": "jonas@tsunami.example", "admin_email": "jonas@tsunami.example"}.items():
        pg.fill(f"#id_{k}", v)
    pg.select_option("#id_country", "DE"); pg.select_option("#id_status", "active")
    pg.click("main button[type=submit]")
    try: pg.wait_for_selector("text=Invitation sent", timeout=5000)
    except Exception: diag(pg, "client_create"); raise
    client_admin_link = pg.input_value("#invite-link")
    pg.click("text=Done")
    client_url = pg.url
    for name, cc in (("Tsunami Axis Germany", "DE"), ("Tsunami Axis France", "FR"), ("Tsunami Axis Luxembourg", "LU")):
        pg.click("text=Add legal entity"); pg.fill("#id_name", name); pg.select_option("#id_country", cc)
        pg.fill("#id_address", "Registered office"); pg.select_option("#id_eudr_role", "operator"); pg.click("main button[type=submit]")
        pg.wait_for_url(client_url)
    pg.click("a.btn:has-text('Invite supplier')")
    pg.fill("#id_supplier_name", "Supplier A Timber"); pg.fill("#id_email", "anna@supplier-a.example")
    pg.check("label:has-text('Tsunami Axis Germany') input")
    pg.click("main button[type=submit]"); pg.wait_for_selector("text=Invitation sent")
    supplier_link = pg.input_value("#invite-link")
    pg.click("text=Done"); pg.screenshot(path=S + "1_client_detail.png", full_page=True)
    c.close()

    # Supplier registers
    c, pg = ctx(); pg.goto(supplier_link); pg.screenshot(path=S + "2_supplier_register.png", full_page=True)
    pg.select_option("#id_company-country", "PL"); pg.fill("#id_company-address", "Ul. Lesna 1, Poznan")
    pg.fill("#id_company-contact_name", "Anna Nowak"); pg.fill("#id_account-full_name", "Anna Nowak")
    pg.fill("#id_account-password1", PW); pg.fill("#id_account-password2", PW)
    pg.click("main button[type=submit]"); pg.wait_for_url(B + "/")
    pg.screenshot(path=S + "3_supplier_dashboard.png", full_page=True)
    # producer
    pg.goto(B + "/producers/new/"); pg.fill("#id_name", "Lasy Wielkopolskie"); pg.select_option("#id_country", "PL")
    pg.click("main button[type=submit]"); pg.wait_for_selector("h1:has-text('Lasy Wielkopolskie')")
    # product
    pg.goto(B + "/products/new/")
    pg.fill("#id_name", "Sawn oak boards"); pg.fill("#id_sku", "OAK-27"); pg.select_option("#id_commodity", "wood")
    pg.fill("#id_cn_code", "4407 91 15"); pg.fill("#id_species_scientific", "Quercus robur")
    pg.check("label:has-text('Lasy Wielkopolskie') input"); pg.select_option("#id_country_of_production", "PL")
    assert pg.is_checked("label:has-text('Tsunami Axis') input"), "single client should be preselected"
    pg.click("main button[type=submit]"); pg.wait_for_selector("h1:has-text('Sawn oak boards')")
    # source plot: draw polygon by clicking on the map
    pg.goto(B + "/sources/new/")
    pg.wait_for_selector(".leaflet-draw-draw-polygon")
    pg.evaluate("document.getElementById('point-lat')")  # page ok
    # zoom map to Poland via paste of a point then clear? Instead zoom programmatically through UI: use +
    box = pg.locator("#plot-map").bounding_box()
    for _ in range(3): pg.click(".leaflet-control-zoom-in"); pg.wait_for_timeout(300)
    pg.click(".leaflet-draw-draw-polygon")
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    pts = [(cx - 80, cy - 60), (cx + 90, cy - 50), (cx + 70, cy + 70), (cx - 60, cy + 80)]
    for x, y in pts: pg.mouse.click(x, y); pg.wait_for_timeout(150)
    pg.mouse.click(*pts[0]); pg.wait_for_timeout(400)
    drawn = pg.input_value("#id_geometry_geojson")
    log.append("drawn geojson type: " + json.loads(drawn)["features"][0]["geometry"]["type"])
    log.append("summary: " + pg.inner_text("#geom-summary").replace("\n", " | "))
    pg.fill("#id_name", "Compartment 14B"); pg.fill("#id_plot_reference", "PL-WLK-14B"); pg.select_option("#id_country", "PL")
    pg.select_option("#id_producer", label="Lasy Wielkopolskie"); pg.check("label:has-text('Sawn oak boards') input")
    pg.screenshot(path=S + "4_plot_drawn.png", full_page=True)
    pg.click("main button:has-text('Save source location')"); pg.wait_for_selector("h1:has-text('Compartment 14B')")
    pg.wait_for_timeout(500)
    log.append("detail polygons on map: " + str(pg.locator("path.leaflet-interactive").count()))
    log.append("detail summary: " + pg.inner_text("#geom-summary").replace("\n", " | "))
    pg.screenshot(path=S + "5_plot_detail.png", full_page=True)
    plot_url = pg.url
    # reopen edit, verify reload, upload GeoJSON replacing it, save
    pg.click("text=Edit location"); pg.wait_for_timeout(500)
    log.append("edit reload polygons: " + str(pg.locator("path.leaflet-interactive").count()))
    open("/tmp/upload.geojson", "w").write(json.dumps({"type": "MultiPolygon", "coordinates": [
        [[[16.90, 52.40], [16.92, 52.40], [16.92, 52.41], [16.90, 52.41], [16.90, 52.40]]],
        [[[16.95, 52.40], [16.96, 52.40], [16.96, 52.41], [16.95, 52.40]]]]}))
    pg.click("summary:has-text('Upload a GeoJSON file')"); pg.set_input_files("#geojson-file", "/tmp/upload.geojson"); pg.wait_for_timeout(500)
    log.append("after upload: " + pg.inner_text("#geom-summary").replace("\n", " | "))
    # bad paste shows error but keeps geometry
    pg.click("summary:has-text('Paste GeoJSON')"); pg.fill("#geojson-paste", '{"type":"LineString","coordinates":[[0,0],[1,1]]}'); pg.click("#load-pasted")
    log.append("paste error: " + pg.inner_text("#map-error"))
    pg.click("main button:has-text('Save source location')"); pg.wait_for_selector("h1:has-text('Compartment 14B')"); pg.wait_for_timeout(400)
    log.append("after upload save: " + pg.inner_text("#geom-summary").replace("\n", " | ") + " / facts area: " + pg.inner_text(".facts"))
    c.close()

    # Client admin accepts and views
    c, pg = ctx(); pg.goto(client_admin_link); pg.fill("#id_full_name", "Jonas Weber"); pg.fill("#id_password1", PW); pg.fill("#id_password2", PW)
    pg.click("main button[type=submit]"); pg.wait_for_url(B + "/")
    pg.screenshot(path=S + "6_client_dashboard.png", full_page=True)
    pg.click("text=Supplier A Timber"); pg.click("text=Compartment 14B"); pg.wait_for_timeout(500)
    log.append("client sees polygons: " + str(pg.locator("path.leaflet-interactive").count()) + " editable tools: " + str(pg.locator(".leaflet-draw-draw-polygon").count()))
    pg.screenshot(path=S + "7_client_plot.png", full_page=True)
    c.close()

    # mobile view
    c = br.new_context(viewport={"width": 390, "height": 844}); pg = c.new_page(); login(pg, "admin@sustainzone.example")
    pg.goto(plot_url); pg.wait_for_timeout(400); pg.screenshot(path=S + "8_mobile_plot.png", full_page=False); c.close()
    br.close()
print("\n".join(log))

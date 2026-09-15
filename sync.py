#!/usr/bin/env python3
"""Reconstruye el catalogo brandeado de Euromaglia: hornea lo nuevo y reescribe el feed.

Corre solo, cada hora, por GitHub Actions. Los datos salen de la Store API de
WooCommerce, que es publica y no pide clave.

Que hace, en orden:
  1. Lee productos y variaciones de /wp-json/wc/store/v1/products.
  2. Hornea el marco que le toca a cada foto que todavia no esta en img/.
  3. Escribe feed_brandeado.csv.

Una fila por VARIACION. El pixel (PixelYourSite) manda el id del producto padre
con content_type=product_group, asi que:
    id            = id de la variacion
    item_group_id = id del padre
Es la misma estructura que el catalogo "Euromaglia Home" que arma AdTribes.

Dos conjuntos de productos en Meta, filtrados por custom_label_0:
    inodoros -> marco con "Instalacion oficial en CABA y GBA"
    resto    -> marco con "Envio gratis", o sin pildora si el producto no
                tiene la etiqueta ENVIO GRATIS en la tienda (revestimiento y el
                Operador EVO, a septiembre 2026)
La instalacion es solo de inodoros: Nacho Minuto, 14/09/2026.

Idempotente: el nombre del archivo es el hash de URL de la foto + marco. Si
cambia la foto o el marco que le toca, se hornea de nuevo.
"""
import csv, hashlib, html, io, json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from hornear import UA, hornear

TIENDA   = "https://euromaglia.com.ar"
API      = TIENDA + "/wp-json/wc/store/v1/products"
BASE_IMG = "https://scalelabs-ar.github.io/euromaglia-catalogo-img/img/"
DIR      = os.path.dirname(os.path.abspath(__file__))
IMGS     = os.path.join(DIR, "img")
MARCOS   = {"inodoros": "marco_inodoros.png",
            "envio_gratis": "marco_envio_gratis.png",
            "sin_pildora": "marco_sin_pildora.png"}
# El feed de AdTribes manda utm_source=Google Shopping y el trafico de Meta
# aparece como Google en GA4. Este no.
UTM      = "utm_source=facebook&utm_medium=paid_social&utm_campaign=catalogo_brandeado"
HILOS, REINTENTOS = 3, 4


def bajar(url, binario=False):
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            d = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
            return d if binario else json.loads(d)
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code == 404:
                raise
        except Exception as e:
            ultimo = e
        time.sleep((2 ** intento) + random.uniform(0, 1))
    raise ultimo


def todos(extra=""):
    """Pagina hasta que una pagina venga con menos de 100."""
    items, pagina = [], 1
    while True:
        lote = bajar(f"{API}?per_page=100&page={pagina}{extra}")
        items += lote
        if len(lote) < 100:
            return items
        pagina += 1


def limpiar(t, limite):
    t = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(t or "")).split())
    return t[: limite - 1] + "…" if len(t) > limite else t


def slug(url, marco):
    return hashlib.sha1(f"{url}|{marco}".encode()).hexdigest()[:16]


def hornear_uno(trabajo, marcos):
    url, marco = trabajo
    destino = os.path.join(IMGS, slug(url, marco) + ".jpg")
    if os.path.exists(destino):
        return "ya estaba"
    try:
        foto = Image.open(io.BytesIO(bajar(url, binario=True)))
        hornear(foto, marcos[marco]).save(destino, quality=92, subsampling=0, optimize=True)
        return "generada"
    except Exception as e:
        print("  ERROR", type(e).__name__, url)
        return "error"


def main():
    os.makedirs(IMGS, exist_ok=True)
    marcos = {k: Image.open(os.path.join(DIR, v)).convert("RGBA") for k, v in MARCOS.items()}

    padres = {p["id"]: p for p in todos()}
    variaciones = todos("&type=variation")
    print(f"productos: {len(padres)} | variaciones: {len(variaciones)}")
    if not padres or not variaciones:
        # Sin esto, un error transitorio de la tienda vacia el feed y Meta lo
        # levanta vacio a la hora siguiente.
        sys.exit("ERROR: la tienda no devolvio productos — no se toca el feed.")

    filas = []
    for v in variaciones:
        p = padres.get(v["parent"])
        if not p:
            continue
        slugs = [c["slug"] for c in p["categories"]]
        tags  = {t["name"].upper() for t in p.get("tags", [])}
        conjunto = "inodoros" if "inodoros" in slugs else "resto"
        if conjunto == "inodoros":
            marco = "inodoros"
        elif "ENVÍO GRATIS" in tags:
            marco = "envio_gratis"
        else:
            marco = "sin_pildora"

        foto = (v.get("images") or p.get("images") or [{}])[0].get("src")
        if not foto:
            continue

        pr = v["prices"]
        esc = 10 ** pr.get("currency_minor_unit", 0)
        regular = int(pr["regular_price"] or pr["price"]) / esc
        actual  = int(pr["price"]) / esc

        cats = [c["name"] for c in p["categories"] if c["slug"] != "todos-los-productos"]
        marca = next((t["name"] for a in p.get("attributes", []) if a.get("taxonomy") == "pa_marca"
                      for t in a["terms"]), "Euromaglia")
        nombre = html.unescape(p["name"])
        detalle = (v.get("variation") or "").split(":", 1)[-1].strip()
        if detalle and len(p.get("variations", [])) > 1:
            nombre = f"{nombre} – {detalle}"
        link = v["permalink"]
        link += ("&" if "?" in link else "?") + UTM

        filas.append({
            "id": str(v["id"]),
            "item_group_id": str(p["id"]),
            "title": limpiar(nombre, 200),
            "description": limpiar(p.get("short_description") or p.get("description") or nombre, 5000),
            "availability": "in stock" if v.get("is_in_stock") else "out of stock",
            "condition": "new",
            "price": f"{regular:.2f} ARS",
            "sale_price": f"{actual:.2f} ARS" if actual < regular else "",
            "link": link,
            "image_link": "",
            "brand": marca,
            "product_type": "Home > " + (cats[0] if cats else "Todos los productos"),
            "custom_label_0": conjunto,
            "custom_label_1": marco,
            "_foto": foto,
            "_marco": marco,
        })

    trabajos = sorted({(f["_foto"], f["_marco"]) for f in filas})
    res = list(ThreadPoolExecutor(HILOS).map(lambda t: hornear_uno(t, marcos), trabajos))
    print(f"fotos: {len(trabajos)} | generadas: {res.count('generada')} | "
          f"ya estaban: {res.count('ya estaba')} | errores: {res.count('error')}")

    sin_marco = 0
    for f in filas:
        foto, marco = f.pop("_foto"), f.pop("_marco")
        archivo = slug(foto, marco) + ".jpg"
        if os.path.exists(os.path.join(IMGS, archivo)):
            f["image_link"] = BASE_IMG + archivo
        else:
            f["image_link"] = foto          # mejor sin marco que roto
            sin_marco += 1

    # Las fotos que ya no usa ningun producto se borran: el repo no crece solo.
    usadas = {os.path.basename(f["image_link"]) for f in filas}
    for a in os.listdir(IMGS):
        if a.endswith(".jpg") and a not in usadas:
            os.remove(os.path.join(IMGS, a))

    filas.sort(key=lambda f: (f["custom_label_0"], f["title"]))
    with open(os.path.join(DIR, "feed_brandeado.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    from collections import Counter
    print(f"-> feed_brandeado.csv: {len(filas)} variaciones | "
          f"{sum(f['availability'] == 'out of stock' for f in filas)} sin stock | {sin_marco} sin marco")
    print("   conjuntos:", dict(Counter(f["custom_label_0"] for f in filas)),
          "| marcos:", dict(Counter(f["custom_label_1"] for f in filas)))


if __name__ == "__main__":
    main()

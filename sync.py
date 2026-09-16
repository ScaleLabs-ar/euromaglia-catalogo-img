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
    resto    -> marco con "Envio gratis"
La instalacion es solo de inodoros: Nacho Minuto, 14/09/2026.

EXCLUIDOS del catalogo por decision de Alvaro (15/09/2026): alfombras, pasto
sintetico (categoria revestimiento) y el Operador EVO. En una foto no se ven
atractivos y ademas no tienen envio gratis. Si aparece un producto nuevo sin la
etiqueta ENVIO GRATIS, NO entra al feed y se avisa en el log: el marco promete
envio gratis y no puede mentir.

Idempotente: el nombre del archivo es el hash de URL de la foto + marco. Si
cambia la foto o el marco que le toca, se hornea de nuevo.
"""
import csv, hashlib, html, io, json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

from PIL import ImageDraw, ImageFont

from hornear import UA, hornear

TIENDA   = "https://euromaglia.com.ar"
API      = TIENDA + "/wp-json/wc/store/v1/products"
BASE_IMG = "https://scalelabs-ar.github.io/euromaglia-catalogo-img/img/"
DIR      = os.path.dirname(os.path.abspath(__file__))
IMGS     = os.path.join(DIR, "img")
MARCOS   = {"inodoros": "marco_inodoros.png",
            "envio_gratis": "marco_envio_gratis.png"}
EXCLUIR_CATEGORIAS = {"revestimiento"}
EXCLUIR_NOMBRE = re.compile(r"alfombra|pasto sint|operador evo", re.I)
# El feed de AdTribes manda utm_source=Google Shopping y el trafico de Meta
# aparece como Google en GA4. Este no.
UTM      = "utm_source=facebook&utm_medium=paid_social&utm_campaign=catalogo_brandeado"
HILOS, REINTENTOS = 3, 4

# Sello de descuento. Sale de la Store API (precio regular vs precio actual), asi
# que si la tienda cambia la oferta el sello cambia solo en la corrida siguiente:
# el porcentaje es parte del nombre del archivo.
DESCUENTO_MIN = 5            # por debajo de esto no se muestra
BRONCE, CREMA = (143, 103, 57), (251, 248, 244)
FUENTE = os.path.join(DIR, "InstrumentSans.ttf")


def sello(img, pct, esc=3):
    """Pildora "-20% OFF" arriba a la izquierda, espejando "Tienda oficial".

    Se dibuja a 3x y se reduce: PIL no suaviza bordes de formas."""
    f = ImageFont.truetype(FUENTE, 40 * esc)
    f.set_variation_by_axes([100, 700])
    texto = f"-{pct}% OFF"
    x0, y0, x1, y1 = f.getbbox(texto)
    pad_x, pad_y = 26 * esc, 14 * esc
    w, h = (x1 - x0) + 2 * pad_x, (y1 - y0) + 2 * pad_y
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=BRONCE + (255,))
    d.text((pad_x - x0, pad_y - y0), texto, font=f, fill=CREMA + (255,))
    capa = capa.resize((w // esc, h // esc), Image.LANCZOS)
    out = img.convert("RGBA")
    out.alpha_composite(capa, (32, 176))
    return out.convert("RGB")


def bajar(url, binario=False):
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            d = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
            if binario:
                return d
            # La tienda a veces contesta 200 con HTML (mantenimiento, WAF). Eso
            # no es un caso de error: hay que reintentar, no abortar la corrida.
            return json.loads(d)
        except json.JSONDecodeError as e:
            ultimo = RuntimeError(f"la tienda devolvio algo que no es JSON: {d[:120]!r}")
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


def slug(url, marco, pct=0):
    clave = f"{url}|{marco}" + (f"|{pct}" if pct else "")
    return hashlib.sha1(clave.encode()).hexdigest()[:16]


def hornear_uno(trabajo, marcos):
    url, marco, pct = trabajo
    destino = os.path.join(IMGS, slug(url, marco, pct) + ".jpg")
    if os.path.exists(destino):
        return "ya estaba"
    try:
        foto = Image.open(io.BytesIO(bajar(url, binario=True)))
        img = hornear(foto, marcos[marco])
        if pct:
            img = sello(img, pct)
        img.save(destino, quality=92, subsampling=0, optimize=True)
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

    filas, excluidas = [], 0
    for v in variaciones:
        p = padres.get(v["parent"])
        if not p:
            continue
        slugs = [c["slug"] for c in p["categories"]]
        tags  = {t["name"].upper() for t in p.get("tags", [])}
        if EXCLUIR_CATEGORIAS & set(slugs) or EXCLUIR_NOMBRE.search(html.unescape(p["name"])):
            excluidas += 1
            continue
        conjunto = "inodoros" if "inodoros" in slugs else "resto"
        if conjunto == "resto" and "ENVÍO GRATIS" not in tags:
            print(f"  OJO: sin etiqueta ENVIO GRATIS, queda afuera — {p['id']} {p['name'][:60]}")
            excluidas += 1
            continue
        marco = "inodoros" if conjunto == "inodoros" else "envio_gratis"

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
            "_pct": (lambda d: d if d >= DESCUENTO_MIN else 0)(round((1 - actual / regular) * 100)) if regular else 0,
        })

    trabajos = sorted({(f["_foto"], f["_marco"], f["_pct"]) for f in filas})
    res = list(ThreadPoolExecutor(HILOS).map(lambda t: hornear_uno(t, marcos), trabajos))
    print(f"fotos: {len(trabajos)} | generadas: {res.count('generada')} | "
          f"ya estaban: {res.count('ya estaba')} | errores: {res.count('error')}")

    sin_marco = 0
    for f in filas:
        foto, marco, pct = f.pop("_foto"), f.pop("_marco"), f.pop("_pct")
        archivo = slug(foto, marco, pct) + ".jpg"
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
          f"{sum(f['availability'] == 'out of stock' for f in filas)} sin stock | {sin_marco} sin marco | {excluidas} excluidas")
    print("   conjuntos:", dict(Counter(f["custom_label_0"] for f in filas)),
          "| marcos:", dict(Counter(f["custom_label_1"] for f in filas)))


if __name__ == "__main__":
    main()

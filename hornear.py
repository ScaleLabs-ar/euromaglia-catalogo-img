#!/usr/bin/env python3
"""Hornea EUROMAGLIA_frame.png sobre las fotos de producto.

A diferencia de Luvia, Plyrap y G4 —donde la foto viene recortada sobre blanco y
se centra dentro de la zona segura— las fotos de Euromaglia son **de ambiente**:
el baño entero está en la imagen. Centrarlas sobre un lienzo blanco dejaba dos
franjas blancas a los costados y la pieza se veía como un recorte pegado.

Acá la foto **cubre** el lienzo entero (escala al lado mayor y recorta el
sobrante, centrado) y el marco se apoya encima. La barra negra y la barra del
pie tapan los bordes, que es justo donde una foto de ambiente tiene menos
información.
"""
import io
import sys
import urllib.request
import cv2
import numpy as np
from PIL import Image

LIENZO = 1080
TOP, BOT = 100, 996        # banda libre entre la barra y el pie del marco
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    # El CDN (ExactDN) devuelve 403 sin referer del propio dominio.
    "Referer": "https://euromaglia.com.ar/",
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


def cubrir(foto, lado=LIENZO):
    """Escala la foto hasta tapar el lienzo y recorta lo que sobra, centrado.

    Las fotos de la tienda son de 600 a 800 px y vienen en WebP de ~13 KB, o sea
    ya traen bloqueo de compresion. El orden de los pasos importa: si se amplia
    primero, los bloques se amplian con la imagen y despues ya no hay como
    sacarlos.

      1. denoise NO local (h=2, suave) para bajar el bloqueo sin comerse bordes
      2. ampliar en dos pasos (cubico 1.35x y despues LANCZOS al destino):
         un salto unico deja mas ringing
      3. unsharp suave sobre el resultado ya limpio

    Con h=3 y un bilateral encima la pared de marmol quedaba plastica, en
    manchones. Suave es mejor que agresivo: no se puede recuperar detalle que la
    foto original no tiene.
    """
    esc = lado / max(foto.width, foto.height)
    a = cv2.cvtColor(np.asarray(foto), cv2.COLOR_RGB2BGR)

    if esc > 1.02:
        a = cv2.fastNlMeansDenoisingColored(a, None, 2, 2, 7, 21)
        medio = (round(a.shape[1] * esc * 0.74), round(a.shape[0] * esc * 0.74))
        a = cv2.resize(a, medio, interpolation=cv2.INTER_CUBIC)

    destino = (max(1, round(foto.width * esc)), max(1, round(foto.height * esc)))
    a = cv2.resize(a, destino, interpolation=cv2.INTER_LANCZOS4)

    if esc > 1.02:
        borroso = cv2.GaussianBlur(a, (0, 0), 1.0)
        a = cv2.addWeighted(a, 1.35, borroso, -0.35, 0)

    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))


def _relleno(borde, largo, suavizado=151, mezcla=0.72):
    """Del borde saca un color por linea: mediana, suavizado y mezclado."""
    n = borde.shape[0]
    col = np.median(borde, axis=1).astype(np.float32)
    col = cv2.GaussianBlur(col.reshape(n, 1, 3), (1, suavizado), 0).reshape(n, 3)
    glob = np.median(borde.reshape(-1, 3), axis=0).astype(np.float32)
    col = col * mezcla + glob * (1 - mezcla)
    return np.repeat(col[:, None, :], largo, axis=1).astype(np.uint8)


def extender(pil, ancho=LIENZO, alto=None, tira=56):
    """Completa lo que le falte a la foto con el COLOR de su propio borde.

    La foto casi nunca tiene la forma de la banda libre del marco, asi que al
    encajarla entera sobra lugar: a los costados si es alta, arriba y abajo si
    es apaisada. Como llenar ese lugar:

      · espejar el borde    -> duplica lo que lo toque (el perfil de la
                               mampara salia dos veces)
      · estirar una tira    -> estrias
      · desenfocar la foto  -> se lee como parche
      · dejarlo liso        -> limpio, pero no llena

    Lo que funciona es tirar la textura y quedarse con el color. Por cada linea
    del borde se toma la MEDIANA de una tira —la mediana ignora un objeto
    oscuro que cruce el borde, cosa que el promedio no hace— y se suaviza con
    un nucleo largo. Queda un degrade que sigue la luz de la foto sin nada
    reconocible como repetido.

    La mezcla con la mediana global evita que una mancha pegada al borde tiña
    toda la extension: sin eso, unas manzanas rojas dejaban una franja rosa.
    """
    alto = alto or ancho
    a = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    h, w = a.shape[:2]
    izq, arr = (ancho - w) // 2, (alto - h) // 2
    out = np.zeros((alto, ancho, 3), np.uint8)
    out[arr:arr + h, izq:izq + w] = a

    if w < ancho:                                   # foto alta: faltan costados
        der = ancho - w - izq
        t = min(tira, w)
        out[arr:arr + h, :izq] = _relleno(a[:, :t], izq)
        out[arr:arr + h, izq + w:] = _relleno(a[:, -t:], der)
    if h < alto:                                    # foto apaisada: falta arriba y abajo
        aba = alto - h - arr
        t = min(tira, h)
        franja = np.transpose(out[arr:arr + t, :, :], (1, 0, 2))
        out[:arr, :] = np.transpose(_relleno(franja, arr), (1, 0, 2))
        franja = np.transpose(out[arr + h - t:arr + h, :, :], (1, 0, 2))
        out[arr + h:, :] = np.transpose(_relleno(franja, aba), (1, 0, 2))

    # funde la costura para que no se vea el corte entre foto y color plano
    fundido = 34
    if w < ancho:
        for k in range(fundido):
            peso = k / fundido
            for x, plano_x in ((izq + k, izq - 1), (izq + w - 1 - k, izq + w)):
                if 0 <= plano_x < ancho:
                    out[arr:arr + h, x] = (out[arr:arr + h, x] * peso +
                                           out[arr:arr + h, plano_x] * (1 - peso)).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def hornear(foto, marco):
    """La foto ENTERA dentro de la banda libre, con los costados completados."""
    banda = BOT - TOP
    f = extender(cubrir(foto.convert("RGB"), banda), LIENZO, banda)
    lienzo = Image.new("RGB", (LIENZO, LIENZO))
    lienzo.paste(f, (0, TOP))
    # arriba y abajo quedan tapados por las barras: se continua con el mismo
    # borde para que no aparezca una franja negra si el marco se corre
    lienzo.paste(f.crop((0, 0, LIENZO, TOP)), (0, 0))
    lienzo.paste(f.crop((0, f.height - (LIENZO - BOT), LIENZO, f.height)), (0, BOT))
    lienzo = lienzo.convert("RGBA")
    lienzo.alpha_composite(marco)
    return lienzo.convert("RGB")


def mejor(urls):
    """De varias variantes de la misma foto, se queda con la de mas pixeles.

    La biblioteca de WordPress tiene el mismo producto subido dos veces: las de
    2024/07 son de 600x600 y las de 2026/05, de 800x800. Tomar la primera que
    aparece cuesta un tercio de resolucion.
    """
    mejorada, area = None, -1
    for u in urls:
        try:
            im = bajar(u)
        except Exception:
            continue
        if im.width * im.height > area:
            mejorada, area = im, im.width * im.height
    if mejorada is None:
        raise RuntimeError("ninguna variante se pudo bajar")
    return mejorada


def bajar(url):
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=60).read()
    return Image.open(io.BytesIO(raw))


if __name__ == "__main__":
    marco = Image.open("EUROMAGLIA_frame.png").convert("RGBA")
    for destino, url in (a.split("=", 1) for a in sys.argv[1:]):
        hornear(bajar(url), marco).save(destino, quality=97, subsampling=0)
        print("ok", destino)

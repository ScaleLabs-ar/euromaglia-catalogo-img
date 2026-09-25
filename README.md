# Euromaglia — catálogo brandeado para Meta

Fotos de producto con el marco de marca horneado y el feed que lee Meta.
Todo se regenera solo cada hora con la Action `sync.yml` (al :10); Meta lee el feed al :20.

| Pieza | Valor |
|---|---|
| Feed | `https://scalelabs-ar.github.io/euromaglia-catalogo-img/feed_brandeado.csv` |
| Catálogo Meta | `1871880627134439` (business Euromaglia `562921224932841`) |
| Fuente de datos | `2293023584829771`, horaria al :20 (Buenos Aires) |
| Píxel conectado | `630213701304113` |
| Conjunto inodoros | `4856253231263300` — `custom_label_0 = inodoros` |
| Conjunto exterior | `1411161431102883` — `custom_label_0 = exterior` |
| Conjunto resto | `1047925054671119` — `custom_label_0 = resto` |

## Tres marcos

| Marco | Píldora | Quién lo lleva |
|---|---|---|
| `marco_inodoros.png` | Instalación oficial en CABA y GBA | categoría `inodoros` |
| `marco_envio_dia.png` | Envío en el día | categoría `muebles` (exterior) |
| `marco_envio_gratis.png` | Envío gratis | resto, con etiqueta ENVÍO GRATIS en la tienda |

Los muebles de exterior salieron de `resto` el 25/09/2026 y arman conjunto propio: mezclados
con sanitarios no se podían comunicar, y el argumento que más tracciona en esa línea es el
plazo de entrega, no el envío gratis (Nacho Minuto). La etiqueta ENVÍO GRATIS solo se exige en
`resto`, que es el único marco que promete precio de envío.

`marco_envio_dia.png` se generó desde `marco_envio_gratis.png` reconstruyendo la píldora con la
geometría real medida píxel a píxel (cuerpo x 33-299, y 865-933, filete de 3 px `#CCBAA4`) y
levantando el camión como máscara de tinta. Un recorte rectangular arrastraba el canto de la
píldora vieja.
Excluidos del feed: alfombras, pasto sintético y Operador EVO (decisión 15/09/2026).

La instalación es solo de inodoros (Nacho Minuto, 14/09/2026). `custom_label_1` dice qué marco llevó cada fila.

## Las tres etiquetas

| Etiqueta | Qué lleva | Para qué |
|---|---|---|
| `custom_label_0` | conjunto: `inodoros` / `exterior` / `resto` | lo que filtran los conjuntos que ya están al aire |
| `custom_label_1` | categoría de la tienda: `duchas`, `griferias`, `baneras`, `bachas`, `muebles`, `inodoros`, `hidromasajes`, `automatismos` | abrir una línea nueva = crear un conjunto, sin tocar este repo |
| `custom_label_2` | marco que llevó la foto | diagnóstico |

`custom_label_0` **no** se abre por categoría a propósito: los conjuntos que hoy entregan filtran
por sus tres valores y cambiarlos los vaciaría.

### La categoría no se lee del producto

El campo `categories` que la Store API devuelve dentro de cada producto **no es confiable**: las 8
bachas lo traen vacío aunque estén en la categoría. Filtrar por `?category=<slug>` sí las devuelve,
y el total coincide con el contador del término en las 9 categorías (verificado 25/09/2026). Por eso
`mapa_categorias()` arma el índice leyendo categoría por categoría.

No es sólo la etiqueta: de esos slugs salen también el conjunto, el marco y la exclusión de
revestimiento. Con el campo del producto, un revestimiento podría colarse sin que nadie lo vea.

## IDs

`id` = variación de WooCommerce, `item_group_id` = producto padre. PixelYourSite manda el padre
en `content_ids` con `content_type=product_group`, que Meta cruza contra `item_group_id`.

Los links llevan `utm_source=facebook&utm_medium=paid_social&utm_campaign=catalogo_brandeado`
(el feed viejo de AdTribes mandaba `utm_source=Google Shopping`).

## Sello de descuento

Si la variante tiene precio de oferta menor al regular (Store API), la foto lleva una píldora
bronce "-20% OFF" arriba a la izquierda. El porcentaje se calcula en cada corrida y es parte del
hash del archivo: si la tienda cambia o saca la oferta, la foto se rehornea sola. Menos de 5% no
se muestra. Tipografía: `InstrumentSans.ttf` (Google Fonts, OFL).

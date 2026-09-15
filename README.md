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
| Conjunto resto | `1047925054671119` — `custom_label_0 = resto` |

## Tres marcos

| Marco | Píldora | Quién lo lleva |
|---|---|---|
| `marco_inodoros.png` | Instalación oficial en CABA y GBA | categoría `inodoros` |
| `marco_envio_gratis.png` | Envío gratis | resto, con etiqueta ENVÍO GRATIS en la tienda |
| `marco_sin_pildora.png` | — | resto sin esa etiqueta (revestimiento y Operador EVO) |

La instalación es solo de inodoros (Nacho Minuto, 14/09/2026). `custom_label_1` dice qué marco llevó cada fila.

## IDs

`id` = variación de WooCommerce, `item_group_id` = producto padre. PixelYourSite manda el padre
en `content_ids` con `content_type=product_group`, que Meta cruza contra `item_group_id`.

Los links llevan `utm_source=facebook&utm_medium=paid_social&utm_campaign=catalogo_brandeado`
(el feed viejo de AdTribes mandaba `utm_source=Google Shopping`).

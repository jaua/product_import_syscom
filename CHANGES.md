# Control de Cambios — Syscom Importador de Productos

## [Pendiente de versión] — 2026-05-03 (revisión 2)

### Bugs corregidos (segunda revisión)

| # | Archivo | Línea | Descripción | Gravedad |
|---|---------|-------|-------------|----------|
| 9  | `models/syscom_parametros.py` | 10–13 | `__init__` definido en medio de los atributos de clase; los atributos posteriores quedaban flotando debajo del método. Reorganizado: todos los atributos de clase primero, luego `__init__` al final | Baja |
| 10 | `models/syscom_config.py` | 580 | `datos_syscom_product` no incluía `syscom_url_imagen`, por lo que `product_url_image` en `product.template` siempre llegaba como `None` al crear o actualizar productos | Alta |
| 11 | `models/syscom_config.py` | 963 | Mutable default arguments `l_productos_creados_vals=[]` y `d_productos_actualizados={}` en `_procesar_info_proveedor`; reemplazados por `None` con inicialización interna | Baja |
| 12 | `models/syscom_config.py` | 98 | `datetime.now()` (hora local del servidor) comparado contra `fecha_descarga` (UTC de Odoo); diferencia de tiempo incorrecta si el servidor no está en UTC. Cambiado a `datetime.utcnow()` | Alta |
| 13 | `models/syscom_config.py` | 420 | `import csv` dentro del método `_crear_categorias` siendo que `csv` ya está importado a nivel de módulo; importación redundante eliminada | Baja |

---

## [Pendiente de versión] — 2026-05-02 (revisión 1)

### Bugs corregidos (primera revisión)

| # | Archivo | Línea | Descripción | Gravedad |
|---|---------|-------|-------------|----------|
| 1 | `models/syscom_config.py` | 805 | `exec_info=True` → `exc_info=True`: el traceback de errores en `_clasificar_syscom_provider` nunca se registraba | Alta |
| 2 | `models/syscom_config.py` | 709, 733 | `linea_datos.get('Imagen Principal')` → `linea_datos.get('syscom_url_imagen')`: la clave en el dict interno ya es `syscom_url_imagen`; el campo siempre llegaba como `None` | Alta |
| 3 | `models/syscom_config.py` | 793 | `producto_id_map[default_code]` podía lanzar `KeyError` si el producto no existía en el mapa; cambiado a `.get()` con skip del registro | Alta |
| 4 | `models/syscom_parametros.py` | — | `_eliminar_archivo_previo` era atributo de clase (estado global mutable compartido); movido a atributo de instancia para evitar efectos secundarios entre ejecuciones | Media |
| 5 | `models/syscom_config.py` | 478–524 | Búsqueda duplicada del proveedor Syscom: se buscaba en `_procesar_csv` y de nuevo en `_leer_csv`; eliminada la búsqueda redundante en `_leer_csv`, se recibe el ID como parámetro | Media |
| 6 | `models/syscom_config.py` | 636 | Mutable default argument `marca_cache={}` en `_set_or_create_brand`; cambiado a `None` con inicialización interna | Baja |
| 7 | `models/syscom_config.py` | 92 | Variable `no_usado = None` declarada y nunca usada; eliminada | Baja |
| 8 | `security/ir.model.access.csv` | — | `base.group_user` tenía acceso total (write/create/unlink) a `syscom.config`, que contiene la URL con posibles credenciales; reducido a solo lectura para usuarios normales | Media |

---

## Historial de versiones previas

### [1.0] — inicial
- Descarga automática de archivos CSV desde Syscom
- Configuración de categorías y márgenes de ganancia
- Bitácora de importaciones (`syscom.log`)
- Actualización automática de productos (`product.template`)
- Modelo separado para datos del proveedor (`product.provider.syscom`)
- Normalización de encoding UTF-8/Latin-1 en CSV descargados

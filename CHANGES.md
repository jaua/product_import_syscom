# Control de Cambios — Syscom Importador de Productos

## [Pendiente de versión] — 2026-06-15 (revisión 5 — bugs y rendimiento)

### Bugs corregidos

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 29 | `models/syscom_config.py` | `_calcular_precios`: en error retornaba `(None, None)` (tupla truthy) → `if not precios:` nunca lo detectaba; cambiado a retornar `None` para que el guard funcione | Alta |
| 30 | `models/syscom_config.py` | `_clasificar_syscom_provider`: `raise UserError` estaba dentro de `if var._logger_info:` — el error solo se lanzaba con logging activo; movido fuera del bloque | Alta |
| 31 | `models/syscom_config.py` | `_limpiar_archivos_antiguos`: condición `ruta_bak == archivo_actual` nunca protegía el respaldo (evaluaba si el archivo actual era un `_bak`, no a la inversa); corregida a `ruta_archivo == archivo_actual + "_bak"` | Media |
| 32 | `models/syscom_config.py` | `var._eliminar_archivo_previo` se escribía sobre la instancia de módulo compartida entre workers de Odoo (race condition); asignaciones eliminadas ya que la bandera nunca se leía para tomar decisiones | Media |
| 33 | `models/syscom_log.py` | Override de `create` eliminado: instanciaba `Parametros()` en cada registro solo para emitir un log que ya existe en `_log_crear`; eliminados también imports de `api` y `Parametros` que quedaron huérfanos | Baja |

### Mejoras de rendimiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 34 | `models/syscom_config.py` | `_clasificar_syscom_provider`: `search([])` reemplazado por búsqueda filtrada por `codigos_a_procesar`; evita cargar toda la tabla en cada importación |
| 35 | `models/syscom_config.py` | Nuevo método `_actualizar_syscom_provider_sql_batch`: actualiza `product.provider.syscom` vía `executemany` SQL con fallback al método individual; también escribe `last_update` |
| 36 | `models/syscom_config.py` | `_procesar_csv` ahora usa `_actualizar_syscom_provider_sql_batch` en lugar de `_actualizar_syscom_provider_individual` |

### Mejoras menores

| #  | Archivo | Descripción |
|----|---------|-------------|
| 37 | `models/syscom_config.py` | `mantener_respaldo` en `_csv_limpiar` ahora condiciona la creación del archivo `_bak`; antes siempre se creaba ignorando el parámetro |
| 38 | `models/syscom_config.py` | `categ_id` incluido en la actualización de productos existentes para mantener la categoría sincronizada con Syscom en cada importación |
| 39 | `models/syscom_config.py` | Typo `mensage` → `mensaje` en `_clasificar_syscom_provider` |
| 40 | `models/syscom_config.py` | `_clasificar_syscom_product`: detecta la categoría raíz de Odoo (`parent_id=False`) una vez antes del loop y la antecede a la ruta del CSV; evita que los niveles de Syscom (ej. "Redes") se creen como categorías raíz huérfanas paralelas a "Todos/All". Agnóstico al idioma; fallback al comportamiento anterior si no hay raíz |

---

## [Pendiente de versión] — 2026-05-06 (revisión 4 — antipatrones)

### Antipatrones corregidos

| #  | Archivo | Descripción | Tipo |
|----|---------|-------------|------|
| 19 | `syscom_config.py` | `_crear_categorias` eliminado (código muerto; nunca se invocaba) | Dead code |
| 20 | `syscom_config.py` | `_asignar_impuestos` eliminado (código muerto; impuestos ya se asignan en `_procesar_batch_creacion`) | Dead code |
| 21 | `syscom_config.py` | `_get_or_create_category_from_parts` ahora recibe `categoria_cache`; elimina N+1 queries al reutilizar búsquedas de categorías entre productos | Rendimiento |
| 22 | `syscom_config.py` | `_csv_limpiar`: fallback `self._ruta_archivo_csv` (atributo inexistente) reemplazado por `ValueError` explícito | Fallo latente |
| 23 | `syscom_config.py` | `tasa_cambio: "0.0"` (string) → `0.0` (float) en creates de `syscom.log` | Tipo incorrecto |
| 24 | `syscom_config.py` | `self.get_config()` sobre `self` eliminado en `ejecutar_importacion` y `_descargar_csv`; se usa `self` directamente | Redundancia |
| 25 | `syscom_config.py` | `lista_categorias_importadas = ''` declarada prematuramente eliminada; se usa `self.categorias_importar` donde se necesita | Claridad |
| 26 | `syscom_config.py` | `menu_nvl1` leído dos veces en `_leer_csv`; segunda lectura redundante eliminada | Redundancia |
| 27 | `syscom_config.py` | `_set_or_create_brand` movido después del check `if not default_code or not name`; evita crear marcas huérfanas | Lógica |
| 28 | `syscom_config.py` | `if (var._usar_bitacora_precios is False):` → `if not var._usar_bitacora_precios:` (3 ocurrencias) | Estilo |

---

## [Pendiente de versión] — 2026-05-06 (revisión 3)

### Bugs corregidos (_clasificar_syscom_provider)

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 14 | `models/syscom_config.py` | `datos_syscom_proveedor=None` causaba `TypeError` silenciosa en el `for`; normalizado a `[]` al inicio del método | Alta |
| 15 | `models/syscom_config.py` | `syscom_inventory` llegaba como `str` desde el CSV pero `fields.Integer` requiere `int`; añadida conversión con fallback a `0` | Alta |
| 16 | `models/syscom_config.py` | `producto_id_map` no se inicializaba si `datos_syscom_proveedor` era falsy, dejando la variable indefinida; inicializado a `{}` al inicio | Media |
| 17 | `models/syscom_config.py` | Contador `omitidos` añadido para registrar en el log cuántos registros se saltaron por `tmpl_id` no encontrado | Baja |
| 18 | `models/syscom_config.py` | Comentarios obsoletos incorrectos eliminados (decían "usar supplierinfo" dentro del modelo que ya es el separado) | Baja |

---

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

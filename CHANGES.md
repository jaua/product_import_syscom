# Control de Cambios — Syscom Importador de Productos

## [Pendiente de versión] — 2026-10-16 (revisión 15)

### Mejoras de comportamiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 67 | `models/syscom_api.py` (nuevo), `models/syscom_importador.py`, `models/syscom_config.py`, `views/syscom_config_views.xml` | Al final de cada importación, se actualiza `product.template.description_ecommerce` (campo de `website_sale`) con el `modelo` y `caracteristicas` obtenidos de la API de ficha de producto de Syscom (`developers.syscom.mx/api/v1/productos/{id}`), para los templates tocados en esa corrida que además estén publicados (`is_published=True`) en la tienda web. `syscom_api.py` aporta las funciones puras `obtener_ficha_producto`/`formatear_descripcion_ecommerce` (el token se recibe como parámetro, no se lee internamente). Nuevo campo `syscom_api_token` en `syscom.config`, restringido a `base.group_system` (`groups=` a nivel de campo, ya que `base.group_user` tiene lectura sobre el resto de la config) y oculto en la UI (`password="True"`). Si el token está vacío, el paso se omite sin afectar el resto de la importación; un fallo por producto (API caída, 404, token inválido) se registra y se continúa con el resto |

## [Pendiente de versión] — 2026-10-16 (revisión 14)

### Reestructuración

| Archivo | Descripción |
|---------|-------------|
| `models/syscom_importador.py` (nuevo), `models/syscom_config.py` | `syscom_config.py` quedaba mezclando dos responsabilidades: los campos de configuración y las ~1500 líneas del proceso de importación (descarga/limpieza de CSV, clasificación, actualización/creación en batch, despublicación web, bitácora, homologación de categorías). Se separan en dos archivos del mismo modelo ORM (`syscom.config`): `syscom_config.py` se queda solo con los 7 campos + `get_config`/`write`/`create`/`_actualizar_nextcall_cron` (ciclo de vida ligado a la config); `syscom_importador.py` extiende el modelo vía `_inherit = 'syscom.config'` con todo el proceso de importación. Sin cambios de comportamiento, vistas, seguridad ni cron — todo sigue siendo el mismo `_name`. `models/__init__.py` importa `syscom_importador` después de `syscom_config` |

## [Pendiente de versión] — 2026-10-16 (revisión 13)

### Reestructuración

| Archivo | Descripción |
|---------|-------------|
| `models/logging_utils.py` (nuevo), `models/syscom_config.py`, `models/csv_utilerias.py`, `models/bitacora_precios.py` | `_FuncNameFilter` (antepone `[nombre_función]` a cada log) se movió de `syscom_config.py` a su propio archivo como `FuncNameFilter`, evitando el import circular que impedía reusarlo. Se aplica ahora también en `csv_utilerias.py` y `bitacora_precios.py`, que antes registraban sus propios `_logger` sin el filtro — sus mensajes no llevaban el prefijo `[función]` que sí tenía el resto del módulo |
| `models/syscom_config.py` | `_elapsed()`: closure idéntica de 2 líneas duplicada en 4 métodos de actualización batch (`_actualizar_productos_individual`, `_actualizar_productos_sql_batch`, `_actualizar_syscom_provider_individual`, `_actualizar_syscom_provider_sql_batch`). Consolidada en una única función de módulo `_segundos_desde(inicio)`. Sin cambios de comportamiento |

## [Pendiente de versión] — 2026-10-16 (revisión 12)

### Reestructuración

| Archivo | Descripción |
|---------|-------------|
| `models/bitacora_precios.py` (nuevo), `models/syscom_config.py` | Las 5 funciones a nivel de módulo (fuera de `SyscomConfig`, sin dependencias del ORM) que implementaban la bitácora de precios y su rotación — `registrar_bitacora_precios`, `comprimir_archivo_zip`, `contar_archivos_patron`, `obtener_primer_archivo`, `bitacora_limpiar_revisar` — se movieron a `models/bitacora_precios.py`, mismo patrón ya usado para `csv_utilerias.py`/`normaliza_csv`. `syscom_config.py` las importa (`from .bitacora_precios import ...`); se eliminan los imports `zipfile`/`glob`/`re`, que ya no se usan ahí. Sin cambios de comportamiento |

## [Pendiente de versión] — 2026-10-16 (revisión 11)

### Bugs corregidos

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 66 | `models/syscom_config.py` | `hora_ejecucion` era un campo decorativo: nada en el código lo leía y el cron (`interval_number=1 days`) ignoraba por completo la hora configurada en la UI. Se agregan overrides de `write`/`create` que, al cambiar `hora_ejecucion`, recalculan `nextcall` del cron a la próxima ocurrencia de esa hora (UTC) — hoy si aún no pasó, mañana en caso contrario. El intervalo diario (`interval_number`/`interval_type`) no se toca; Odoo sigue calculando los siguientes disparos sumándolo a partir de este `nextcall` re-anclado | Media |

## [Pendiente de versión] — 2026-10-16 (revisión 10)

### Mejoras de comportamiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 64 | `models/product_provider_syscom.py`, `models/syscom_config.py` | Nuevo campo `es_kit` en `product.provider.syscom`, poblado desde la columna "Es Kit" del CSV de Syscom. Se escribe tanto en la creación (ORM) como en la actualización en batch (SQL directo) de registros de proveedor |
| 65 | `models/syscom_config.py`, `__manifest__.py` | Nuevo método `_actualizar_publicacion_web_batch`: despublica de la tienda web (`is_published=False`) los `product.template` cuya existencia total reportada en el CSV de la importación actual es 0, sumando existencia entre todos sus registros de proveedor syscom (`d_tmpl_existencia`, devuelto por `_clasificar_syscom_provider`). Solo actúa sobre templates presentes en el CSV; nunca publica automáticamente — un template con existencia > 0 conserva su estado de publicación actual, ya que publicar sigue siendo decisión manual. Requiere la nueva dependencia `website_sale` (campo `is_published`) |



### Bugs corregidos

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 56 | `models/syscom_config.py` | `bitacora_limpiar_revisar`: el archivo de bitácora de precios nunca se truncaba tras comprimirse a `.zip`, por lo que la "rotación" no rotaba nada y se re-comprimía un archivo cada vez más grande en cada importación | Alta |
| 57 | `models/syscom_config.py` | `bitacora_limpiar_revisar`: `contar_archivos_patron`/`obtener_primer_archivo` recibían la ruta absoluta completa como patrón (en vez del basename), generando una ruta duplicada inválida que nunca coincidía con ningún archivo real — el conteo de versiones nunca disparaba la limpieza | Alta |
| 58 | `models/syscom_config.py` | `bitacora_limpiar_revisar`: `os.path.join` recibía el objeto función `obtener_primer_archivo` en vez de la variable con el resultado — lanzaba `TypeError` siempre y ningún `.zip` viejo llegaba a borrarse | Alta |
| 59 | `models/syscom_config.py` | `bitacora_limpiar_revisar`: llamadas a `_logger.info`/`_logger.error` con dos f-strings como argumentos posicionales separados generaban errores internos de logging en vez de mostrar el mensaje esperado | Media |

### Mejoras de comportamiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 60 | `models/syscom_config.py` | `bitacora_limpiar_revisar`: agregado guard de archivo inexistente (evita `FileNotFoundError` en la primera ejecución); el límite de versiones ahora se aplica en `while` en vez de `if` (corrige el invariante en una sola corrida si se acumularon más archivos de los permitidos); eliminado `pass` sobrante |
| 61 | `models/product_template.py`, `models/syscom_config.py` | `product_url_ref`/`product_url_image` en `product.template` dejan de almacenarse directamente y pasan a ser campos computados desde `product.provider.syscom` (fuente única de verdad), eliminando la escritura duplicada del mismo dato en dos modelos durante la importación |
| 62 | `models/syscom_config.py` | `_actualizar_syscom_provider_sql_batch`: al actualizar `product.provider.syscom` vía SQL directo (sin pasar por el ORM), se invalida explícitamente la caché de `product_url_ref`/`product_url_image` en `product.template`, ya que su recompute automático no se dispara con SQL crudo |
| 63 | `security/ir.model.access.csv` | Nuevo acceso de solo lectura para `base.group_user` en `product.provider.syscom`: necesario porque el campo computado de `product.template` (visible para cualquier usuario) ahora lee ese modelo, que antes solo tenía acceso para `base.group_system` |

---

## [Pendiente de versión] — 2026-06-19 (revisión 8)

### Mejoras de comportamiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 54 | `models/syscom_config.py` | `_clasificar_syscom_product`: detección de categoría raíz ahora prioriza el nombre según el idioma del usuario ejecutor — "Todos" para `es_*`, "All" para otros; fallback a cualquier categoría con `parent_id=False`. El idioma se registra en el log para diagnóstico |
| 55 | `models/syscom_config.py`, `views/syscom_config_views.xml` | Nuevo método `homologar_categorias` + botón "Homologar Categorías" en el header del formulario. Migra todos los productos cuya categoría esté fuera de la jerarquía Todos/All: busca equivalente por nombre normalizado (sin acentos, case-insensitive); si no existe, crea `Todos/All/Varios/{nombre}`. Actualiza productos en SQL batch por grupo de destino, luego elimina categorías vacías bottom-up iterativo. Registra resumen en `syscom.log` y muestra notificación con totales |

---

## [Pendiente de versión] — 2026-06-17 (revisión 7)

### Bugs corregidos

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 52 | `models/syscom_config.py` | `ejecutar_importacion`: sin guard de concurrencia — dos workers o un cron + botón manual podían correr simultáneamente corrompiendo datos; agregado `pg_try_advisory_xact_lock` al inicio; si ya hay lock: UI lanza `UserError` claro, cron emite warning y retorna sin error | Alta |
| 53 | `models/syscom_config.py` | `_descargar_csv` sobreescribía `self.tasa_cambio` en BD con la tasa del sistema Odoo en cada importación, destruyendo el valor configurado por el usuario en la UI (conflicto con MEJORA-46); eliminada la escritura. Agregado `_tasa_efectiva()` con prioridad explícita: CSV → sistema Odoo → UI. Usado en `_calcular_precios` y `_registrar_log_importacion`. Actualizado `help` del campo | Alta |

---

## [Pendiente de versión] — 2026-06-16 (revisión 6 — bugs críticos + mejoras)

### Bugs corregidos

| #  | Archivo | Descripción | Gravedad |
|----|---------|-------------|----------|
| 41 | `models/syscom_config.py` | `_actualizar_productos_sql_batch`: `categ_id` no se incluía en el SQL UPDATE (MEJORA-38 sin efecto); agregado al SET con `COALESCE` para no sobreescribir con NULL cuando no hay categoría | Alta |
| 42 | `models/syscom_config.py` | `_clasificar_syscom_provider`: `raise UserError` dentro del `try` era tragado por el `except Exception` y se lograba silenciosamente; validación movida antes del `try` | Alta |

### Mejoras de rendimiento / comportamiento

| #  | Archivo | Descripción |
|----|---------|-------------|
| 43 | `models/syscom_config.py` | `_leer_csv`: verificación de `product.brand` en registry movida a una sola vez antes del loop; antes se emitía un warning por cada fila del CSV cuando el módulo no estaba instalado |
| 44 | `models/syscom_config.py` | `_descargar_csv`: `timeout=300` hardcodeado reemplazado por `var._tiempo_espera_descarga` (parámetro configurable de `SyscomParametros`) |
| 45 | `models/syscom_config.py` | `_leer_csv`: `lista_codigos_procesados` deduplicada con `dict.fromkeys` antes de retornar; un CSV con el mismo `default_code` dos veces generaba entradas duplicadas innecesarias |

### Vistas

| #  | Archivo | Descripción |
|----|---------|-------------|
| 46 | `views/syscom_config_views.xml` | Campo `tasa_cambio` visible en el formulario de `syscom.config` cuando `usd_a_mxn` está activo |
| 47 | `views/syscom_log_views.xml` | Campo `tasa_cambio` agregado a la vista de lista y formulario de `syscom.log` |

### Documentación / limpieza

| #  | Archivo | Descripción |
|----|---------|-------------|
| 48 | `models/syscom_parametros.py` | Atributos sin uso documentados como "reservados para implementación futura" con descripción de su propósito pendiente |
| 49 | `models/csv_utilerias.py` | `var = Parametros()` movido a nivel de módulo; antes se instanciaba una nueva `Parametros()` en cada llamada a `normaliza_csv` |
| 50 | `models/syscom_config.py` | `ejecutar_importacion`: eliminada asignación muerta `ruta_archivo_previo = ""` (sobreescrita inmediatamente en la línea siguiente) |
| 51 | `models/syscom_config.py` | `_calcular_precios`: simplificado de `resultado = None` / `resultado = (x, y)` / `return resultado` a `return (standard_price, list_price)` directo |

---

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

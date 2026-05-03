# Control de Cambios — Syscom Importador de Productos

## [Pendiente de versión] — 2026-05-02

### Bugs corregidos

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

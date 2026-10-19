Un sencillo script, para importar de la cuenta de syscom los productos a odoo y actualizar los precios.
No esta completo, varios problemas que resolver, usalo si gustas como ejemplo, no te confies.

## Instalación

Además de instalar el módulo normalmente, dos funciones que corren al final de cada importación
dependen de la API de ficha de producto de Syscom (developers.syscom.mx) y por lo tanto de un
Bearer token montado vía volumen de Docker:

- Actualización de `description_ecommerce` (ver `CHANGES.md`, MEJORA-67/68).
- Despublicación de productos ausentes del CSV por más de "Días máximos de ausencia"
  (`dias_ausencia_maxima`), que usa la API para confirmar que el producto realmente fue
  descontinuado antes de despublicarlo (ver MEJORA-69/70).

Detalles del archivo de token:

- Ruta dentro del contenedor: **`/mnt/DATA/token.dat`** (fija en código —
  `syscom_parametros.SyscomParametros._ruta_token_bearer` — no es un campo configurable en la UI,
  a propósito: cambiarla ahí sin remontar el volumen rompería la integración).
- Contenido: solo el token, sin el prefijo `Bearer` (se agrega al hacer la llamada).
- Si el archivo no existe o está vacío, ambos pasos se omiten silenciosamente (se registra un
  warning en el log); el resto de la importación de productos sigue funcionando normalmente.

Ejemplo de entrada en `docker-compose.yml` del servicio `web`:

```yaml
volumes:
  - /ruta/en/el/host/token.dat:/mnt/DATA/token.dat:ro
```

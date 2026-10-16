Un sencillo script, para importar de la cuenta de syscom los productos a odoo y actualizar los precios.
No esta completo, varios problemas que resolver, usalo si gustas como ejemplo, no te confies.

## Instalación

Además de instalar el módulo normalmente, la actualización de `description_ecommerce` al final
de la importación (ver `CHANGES.md`, MEJORA-67/68) requiere montar un volumen de Docker con el
Bearer token de la API de Syscom (developers.syscom.mx) en texto plano:

- Ruta dentro del contenedor: **`/mnt/DATA/token.dat`** (fija en código —
  `syscom_parametros.SyscomParametros._ruta_token_bearer` — no es un campo configurable en la UI,
  a propósito: cambiarla ahí sin remontar el volumen rompería la integración).
- Contenido: solo el token, sin el prefijo `Bearer` (se agrega al hacer la llamada).
- Si el archivo no existe o está vacío, ese paso se omite silenciosamente (se registra un
  warning en el log); el resto de la importación de productos sigue funcionando normalmente.

Ejemplo de entrada en `docker-compose.yml` del servicio `web`:

```yaml
volumes:
  - /ruta/en/el/host/token.dat:/mnt/DATA/token.dat:ro
```

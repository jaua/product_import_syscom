
# ===========================
# models/syscom_api.py
# ===========================
"""Cliente de la API de detalle de producto de Syscom
(https://developers.syscom.mx/api/v1/productos/{id}) y formateo del HTML
de description_ecommerce a partir de su respuesta. Sin dependencias del
ORM de Odoo — el token se recibe como parámetro en vez de leerse de la
configuración, para que estas funciones sean puras y reusables.
"""
import html as html_lib
import logging
import requests
from .logging_utils import FuncNameFilter
from .syscom_parametros import SyscomParametros as Parametros

_logger = logging.getLogger(__name__)
_logger.addFilter(FuncNameFilter())
var = Parametros()

SYSCOM_API_PRODUCTOS_URL = 'https://developers.syscom.mx/api/v1/productos'
_TIMEOUT_API_FICHA = 30  # segundos; igual orden que _TIMEOUT_DESCARGA_IMAGEN en product_syscom_update_image


def leer_token_bearer(ruta=None) -> str:
    """Lee el Bearer token de la API de Syscom desde un archivo plano —
    por defecto var._ruta_token_bearer ("/mnt/DATA/token.dat"), montado vía
    volumen de Docker. Deliberadamente NO se almacena en syscom.config: así
    el token nunca queda en la base de datos ni es visible desde la UI.
    Returns:
        str: contenido del archivo sin espacios/saltos de línea al borde, o
        '' si el archivo no existe o no se puede leer (se registra un
        warning; el llamador decide si omitir el paso que lo necesita).
    """
    ruta = ruta or var._ruta_token_bearer
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError as e:
        _logger.warning('No se pudo leer el token Bearer desde %s: %s', ruta, e)
        return ''


def obtener_ficha_producto(id_syscom, token, timeout=_TIMEOUT_API_FICHA) -> dict:
    """Consulta la ficha de un producto en la API de Syscom.
    Args:
        id_syscom (str): producto_id de Syscom (ver product.provider.syscom.id_syscom).
        token (str): Bearer token de la API (developers.syscom.mx).
        timeout (int): segundos de espera antes de abortar la petición.
    Returns:
        dict: JSON de respuesta (incluye al menos 'modelo' y 'caracteristicas').
    Lanza requests.RequestException / ValueError si la petición o el parseo fallan;
    el llamador decide cómo manejar el fallo por producto (ver _sincronizar_descripcion_ecommerce).
    """
    url = f'{SYSCOM_API_PRODUCTOS_URL}/{id_syscom}?iva=1&inventarios=1'
    response = requests.get(
        url,
        headers={'Authorization': f'Bearer {token}'},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def formatear_descripcion_ecommerce(modelo, caracteristicas) -> str:
    """Construye el HTML de description_ecommerce a partir de 'modelo'
    (subtítulo) y 'caracteristicas' (lista de strings -> <ul><li>...).
    Escapa el texto para no romper el HTML con caracteres como < > &.
    Returns:
        str: HTML listo para escribir en product.template.description_ecommerce,
        o '' si no hay nada que mostrar (modelo vacío y sin características).
    """
    partes = []
    if modelo:
        partes.append(f'<h4>Modelo: {html_lib.escape(str(modelo))}</h4>')

    items = [c for c in (caracteristicas or []) if c]
    if items:
        lis = ''.join(f'<li>{html_lib.escape(str(c))}</li>' for c in items)
        partes.append(f'<ul>{lis}</ul>')

    return ''.join(partes)

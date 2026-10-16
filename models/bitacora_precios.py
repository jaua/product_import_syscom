
# ===========================
# models/bitacora_precios.py
# ===========================
"""Utilidades de bitácora de precios: registro en archivo plano y rotación
por tamaño (compresión a .zip + límite de versiones históricas). Sin
dependencias del ORM de Odoo — extraído de syscom_config.py para separar
esta responsabilidad de utilería de archivos del modelo syscom.config.
"""
from datetime import datetime
from .syscom_parametros import SyscomParametros as Parametros
import glob
import logging
import os
import re
import zipfile

_logger = logging.getLogger(__name__)
var = Parametros()


def registrar_bitacora_precios(mensaje):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(var._ruta_descarga, exist_ok=True)
        with open(var._archivo_bitacora_precios, 'a') as f:
            f.write(f'[{timestamp}] {mensaje}\n')
    except Exception as e:
        _logger.error(f'Error al registrar en bitácora de precios: {str(e)}')


def comprimir_archivo_zip(ruta_origen, ruta_destino=None):
    """Comprime un archivo usando zipfile (solo stdlib de Python)."""
    if ruta_destino is None:
        ruta_destino = ruta_origen + ".zip"

    with zipfile.ZipFile(ruta_destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(ruta_origen, arcname=os.path.basename(ruta_origen))

    return ruta_destino


def contar_archivos_patron(directorio, patron="archivos_*.zip"):
    """Cuenta archivos que coincidan con un patrón tipo glob."""
    ruta_patron = f"{directorio.rstrip('/')}/{patron}"
    archivos = glob.glob(ruta_patron)
    return len(archivos)


def obtener_primer_archivo(directorio, patron_nombre, formato_fecha="%d%m%Y%H%M%S"):
    """Devuelve el archivo más antiguo en `directorio` que coincida con `patron_nombre`,
    ordenado por la fecha embebida en el nombre (no alfabéticamente).

    :param directorio: carpeta donde buscar.
    :param patron_nombre: patrón con {fecha} como placeholder de la parte de fecha.
                           Ej: "archivos_{fecha}.zip"
    :param formato_fecha: formato strptime de la parte {fecha}. Ej: "%d%m%Y%H%M%S"
    :return: nombre del archivo más antiguo, o None si no hay coincidencias.
    """
    # Construye el regex a partir del patrón, escapando todo lo literal
    # y reemplazando {fecha} por un grupo capturable de longitud variable.
    partes = patron_nombre.split("{fecha}")
    if len(partes) != 2:
        raise ValueError("patron_nombre debe contener exactamente un {fecha}")

    prefijo_regex = re.escape(partes[0])
    sufijo_regex = re.escape(partes[1])
    regex = re.compile(f"^{prefijo_regex}(.+?){sufijo_regex}$")

    candidatos = []

    for nombre in os.listdir(directorio):
        match = regex.match(nombre)
        if match:
            timestamp_str = match.group(1)
            try:
                fecha = datetime.strptime(timestamp_str, formato_fecha)
                candidatos.append((fecha, nombre))
            except ValueError:
                continue  # coincide el patrón pero la fecha no es válida

    if not candidatos:
        return None

    return min(candidatos, key=lambda x: x[0])[1]


def bitacora_limpiar_revisar():
    """Revisa los límites de volumen del histórico de bitácoras: cuando el
    archivo de bitácora de precios supera el tamaño máximo configurado, se
    comprime a un .zip y se trunca el original para que vuelva a crecer
    desde cero. Solo se conservan hasta `_archivo_bitacora_max_vers` de
    estos .zip históricos (los más antiguos se eliminan), límites
    definidos en syscom_parametros.py.
    """
    try:
        if not os.path.exists(var._archivo_bitacora_precios):
            return

        max_size_bytes = var._archivo_bitacora_max_tamm * 1024 * 1024
        archivo_tamano = os.path.getsize(var._archivo_bitacora_precios)

        if archivo_tamano > max_size_bytes:
            version_archivo = datetime.now().strftime("%d%m%Y%H%M%S")
            archivo_comprimido = f"{var._archivo_bitacora_precios}_{version_archivo}.zip"

            if var._logger_info:
                _logger.info(
                    "Archivo de bitácora (%.2f MB) excede el tamaño máximo (%.2f MB); comprimiendo a %s",
                    archivo_tamano / (1024 * 1024),
                    max_size_bytes / (1024 * 1024),
                    archivo_comprimido,
                )
            comprimir_archivo_zip(var._archivo_bitacora_precios, archivo_comprimido)
            # BUG corregido: antes el archivo original nunca se truncaba tras
            # comprimirlo, así que la "rotación" no rotaba nada — se
            # re-comprimía el mismo archivo, cada vez más grande, en cada
            # importación, sin que el original dejara de crecer.
            open(var._archivo_bitacora_precios, 'w').close()

        # BUG corregido: _archivo_bitacora_precios ya es una ruta absoluta;
        # pasarla completa como patrón a contar_archivos_patron/obtener_primer_archivo
        # (que anteponen el directorio ellos mismos) generaba una ruta duplicada
        # inválida que nunca coincidía con ningún archivo real. Se usa el
        # basename para construir los patrones correctamente.
        patron_basename = os.path.basename(var._archivo_bitacora_precios)
        patron_glob = f"{patron_basename}_*.zip"
        patron_nombre = f"{patron_basename}_{{fecha}}.zip"

        while contar_archivos_patron(var._ruta_descarga, patron_glob) > var._archivo_bitacora_max_vers:
            primer_archivo = obtener_primer_archivo(
                var._ruta_descarga,
                patron_nombre=patron_nombre,
                formato_fecha="%d%m%Y%H%M%S",
            )
            if not primer_archivo:
                break
            # BUG corregido: se pasaba el objeto función `obtener_primer_archivo`
            # en vez de la variable `primer_archivo` con el nombre de archivo
            # resultante — os.path.join lanzaba TypeError siempre y ningún
            # archivo viejo llegaba a borrarse.
            ruta_completa = os.path.join(var._ruta_descarga, primer_archivo)
            os.remove(ruta_completa)
            if var._logger_info:
                _logger.info('Bitácora histórica eliminada por límite de versiones: %s', ruta_completa)

    except Exception as e:
        _logger.error('Error al acceder a los archivos de bitácora de precios: %s', str(e), exc_info=True)

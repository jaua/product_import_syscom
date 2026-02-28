from pathlib import Path
import logging

_logger = logging.getLogger(__name__)


def decodifica_linea(linea_de_texto: bytes) -> str:
    """
    Intenta UTF-8 primero. Si falla, intenta Latin-1/cp1252.
    Caracteres verdaderamente irrecuperables → U+FFFD
    """
    # 1. Intento UTF-8 estricto
    try:
        return linea_de_texto.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 2. Intento cp1252 (superset de Latin-1, cubre más casos Windows)
    try:
        texto = linea_de_texto.decode("cp1252")
        # Validación opcional: re-encodear a UTF-8 para confirmar que
        # los caracteres resultantes son "reales" y no basura visual
        texto.encode("utf-8")  # siempre pasa si decode cp1252 tuvo éxito
        return texto
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # 3. Último recurso: UTF-8 con reemplazo → introduce U+FFFD (�)
    return linea_de_texto.decode("utf-8", errors="replace")


def normaliza_csv(ruta_de_entrada: str, ruta_de_salida: str) -> None:
    archivo_entrada = Path(ruta_de_entrada)
    archivo_salida = Path(ruta_de_salida)

    lineas_corregidas = 0
    lineas_reemplazadas = 0

    with archivo_entrada.open("rb") as file_in, \
         archivo_salida.open("w", encoding="utf-8", newline="") as file_out:

        for i, raw_line in enumerate(file_in, 1):
            # Detectar qué camino tomó la decodificación
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                line = decodifica_linea(raw_line)
                if "\\ufffd" in line or "\ufffd" in line:
                    _logger.warning(f"  [WARN] Línea {i}: caracteres irrecuperables → sustituidos con U+FFFD")
                    lineas_reemplazadas += 1
                else:
                    lineas_corregidas += 1

            file_out.write(line)

    _logger.info(f"\nArchivo normalizado: {ruta_de_salida}")
    _logger.info(f"Líneas re-codificadas desde Latin-1 : {lineas_corregidas}")
    _logger.info(f"Líneas con sustitución U+FFFD       : {lineas_reemplazadas}")

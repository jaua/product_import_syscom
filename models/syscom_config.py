
# ===========================
# models/syscom_config.py
# ===========================
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
from .csv_utilerias import normaliza_csv
from .syscom_parametros import SyscomParametros as Parametros
import requests
import csv
import os
import logging
import shutil
from psycopg2.errors import UniqueViolation

var = Parametros()
_logger = logging.getLogger(__name__)


class _FuncNameFilter(logging.Filter):
    def filter(self, record):
        if var._logger_funcname:
            record.msg = f'[{record.funcName}] {record.msg}'
        return True


_logger.addFilter(_FuncNameFilter())



def registrar_bitacora_precios(mensaje):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(var._ruta_descarga, exist_ok=True)
        with open(var._archivo_bitacora_precios, 'a') as f:
            f.write(f'[{timestamp}] {mensaje}\n')
    except Exception as e:
        _logger.error(f'Error al registrar en bitácora de precios: {str(e)}')


class SyscomConfig(models.Model):
    _name = 'syscom.config'
    _description = 'Configuración de Syscom'
    _rec_name = 'syscom_url_csv'

    syscom_url_csv = fields.Char(
        string='Syscom URL CSV',
        required=True,
        help='URL del archivo CSV de Syscom'
    )
    periodo_segundos = fields.Integer(
        string='Periodo (segundos)',
        default=3600,
        required=True,
        help='Tiempo entre descargas automáticas en segundos'
    )
    hora_ejecucion = fields.Float(
        string='Hora de ejecución',
        default=2.0,
        required=True,
        help='Hora del día para ejecutar la importación automática (formato 24h)'
    )
    categorias_importar = fields.Text(
        string='Lista de categorías a importar',
        help='Categorías separadas por comas y delimitadas por comillas. Dejar vacío para importar todo.'
    )
    ganancia_porcentaje = fields.Float(
        string='Ganancia (%)',
        default=15.0,
        required=True,
        help='Porcentaje de ganancia para calcular el precio de venta'
    )
    usd_a_mxn = fields.Boolean(
        string='Convertir USD a MXN',
        default=False,
        help='Marcar si los precios en el CSV están en dólares y deben convertirse a MXN.'
    )
    tasa_cambio = fields.Float(
        string='Tasa de cambio (USD → Moneda local)',
        default=1.0,
        help='Respaldo: tasa para convertir precios en USD a MXN si no se encuentre en el CSV.'
    )

    @api.model
    def get_config(self):
        """Obtener la configuración activa"""
        config = self.search([], limit=1)
        if not config:
            raise UserError('No hay configuración de Syscom definida.')
        return config

    def ejecutar_importacion(self):
        """Ejecutar el proceso de importación manualmente"""
        self.ensure_one()
        try:
            if var._logger_info:
                _logger.info('Iniciando importación manual desde Syscom')

            tiempo_limite_seg = self.periodo_segundos
            diferencia = 3600  # Valor inicial alto
            reutilizar_archivo = False

            last_log = self.env['syscom.log'].search(
                [('tipo_accion', '=', 'Descarga CSV')],
                limit=1,
                order='fecha_descarga desc')

            now = fields.Datetime.now()
            ruta_archivo_previo = last_log.ruta_archivo if last_log else ""

            if last_log and last_log.fecha_descarga and last_log.ruta_archivo:
                # Calcular diferencia de tiempo (ambos en UTC)
                diferencia = (now - last_log.fecha_descarga).total_seconds()
            else:
                if var._logger_info:
                    _logger.info("Syscom: No se encontraron registros"
                                 " previos de descarga en la bitácora.")
                diferencia = tiempo_limite_seg + 1  # Forzar descarga

            if var._logger_info:
                _logger.info("Syscom: Última descarga fue hace %ss",
                             int(diferencia))
            # Reutilizar archivo si la última descarga fue dentro del
            # período límite y el archivo existe.
            if diferencia < tiempo_limite_seg:
                if os.path.exists(last_log.ruta_archivo):
                    reutilizar_archivo = True
                    ruta_archivo_previo = last_log.ruta_archivo
                else:
                    reutilizar_archivo = False
            else:
                reutilizar_archivo = False

            if reutilizar_archivo:
                # Si reutilizamos, simplemente procesamos
                if var._logger_info:
                    _logger.info("Syscom: Reutiliza archivo descargado previamente: %s",
                                 ruta_archivo_previo)
                archivo_ruta = ruta_archivo_previo
            else:
                # Proceder con la descarga normal
                if var._logger_info:
                    _logger.info("Syscom: Iniciando nueva descarga del archivo CSV...")
                archivo_ruta = self._descargar_csv()
                if var._logger_info:
                    _logger.info("Syscom: Archivo descargado en: %s", archivo_ruta)

            if archivo_ruta == "NoCSV":
                _logger.error("Syscom: El archivo descargado no es un CSV válido. Verifique la URL y el acceso al recurso.")
                # BUG-32: var._eliminar_archivo_previo eliminado — era escritura sobre instancia
                # compartida a nivel de módulo (race condition entre workers); la bandera
                # nunca se leía para tomar decisiones reales.
                raise ValueError("No se descargo el csv correctamente.")

            self._csv_limpiar(archivo_ruta, mantener_respaldo=True)

            if var._logger_info:
                _logger.info("Syscom: Procesando el archivo CSV: %s", archivo_ruta)

            self._procesar_csv(archivo_ruta)

            self._limpiar_archivos_antiguos(archivo_ruta)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Importación Exitosa',
                    'message': 'Los productos han sido importados correctamente',
                    'type': 'success',
                    'sticky': False,
                    }
                }
        except Exception as e:
            _logger.error(f'Error en importación: {str(e)}')
            raise UserError(f'Error al importar productos: {str(e)}')

    def _descargar_csv(self):
        """Descargar el archivo CSV desde la URL configurada"""
        previous_log = None
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/csv,application/csv,text/plain,*/*',
                'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
                'Connection': 'keep-alive',
            }

            if var._logger_info:
                _logger.info(f"Descargando CSV desde: {str(self.syscom_url_csv)[:100]}...")

            # Buscar última descarga válida en la bitácora para usar como respaldo
            previous_log = self.env['syscom.log'].search([
                ('tipo_accion', '=', 'Descarga CSV')
            ], limit=1, order='fecha_descarga desc')

            previous_file = None

            if previous_log and previous_log.ruta_archivo and os.path.exists(previous_log.ruta_archivo):
                previous_file = previous_log.ruta_archivo
                if var._logger_info:
                    _logger.info(f"Syscom: Archivo previo disponible para respaldo: {previous_file}")

            self.tasa_cambio = round((var._mxn_valor /
                                      self.env.ref('base.USD').rate),
                                     var._digitos_redondeo)

            start_time = fields.Datetime.now()
            last_print_time = start_time
            last_print_size = 0
            total_size = 0

            def print_progress(current_size, total_size=None):
                nonlocal last_print_time, last_print_size

                current_time = fields.Datetime.now()
                elapsed = (current_time - start_time).total_seconds()

                speed_mbps = (current_size / elapsed) / (1024 * 1024) if elapsed > 0 else 0

                if total_size:
                    progress_msg = f"{(current_size / total_size) * 100:.1f}%"
                else:
                    progress_msg = f"{current_size / (1024 * 1024):.2f} MB"

                should_print = (
                    (current_size - last_print_size) >= (1024 * 1024) or
                    (current_time - last_print_time).total_seconds() >= var._periodo_actualizaciones
                )

                if should_print:
                    if var._logger_info:
                        _logger.info(
                            f"Descargando: {progress_msg} | "
                            f"Velocidad: {speed_mbps:.2f} MB/s | "
                            f"Tiempo: {elapsed:.0f}s"
                        )
                    last_print_time = current_time
                    last_print_size = current_size
            # def print_progress

            response = requests.get(
                str(self.syscom_url_csv),
                headers=headers,
                timeout=var._tiempo_espera_descarga,  # MEJORA-44: usa el parámetro configurable
                stream=True,
                allow_redirects=True
            )

            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '')
            total_size = int(response.headers.get('content-length', 0))

            if total_size:
                if var._logger_info:
                    _logger.info(f"Tamaño total del archivo: {total_size / (1024*1024):.2f} MB")

            if 'text/html' in content_type:
                _logger.error(
                    "Syscom Error: El servidor devolvió HTML (posible bloqueo o página de login).")
                if previous_file:
                    _logger.warning('Respuesta HTML recibida; se utilizará el archivo previo registrado como respaldo.')
                    return previous_file
                return "NoCSV"

            download_dir = var._ruta_descarga
            os.makedirs(download_dir, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{var._archivo_csv_prefijo}{timestamp}{var._archivo_csv_extension}'
            file_path = os.path.join(download_dir, filename)

            downloaded = 0
            chunk_size = 8192  # 8 KB por chunk

            if var._logger_info:
                _logger.info("Iniciando descarga...")

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        print_progress(downloaded, total_size)

            end_time = fields.Datetime.now()
            total_elapsed = (end_time - start_time).total_seconds()
            avg_speed = downloaded / total_elapsed if total_elapsed > 0 else 0

            if var._logger_info:
                _logger.info(
                    "DESCARGA COMPLETADA — "
                    "Archivo: %s | Tamaño: %.2f MB | "
                    "Tiempo: %.1f s | Velocidad: %.2f MB/s | Ruta: %s",
                    filename,
                    downloaded / (1024 * 1024),
                    total_elapsed,
                    avg_speed / (1024 * 1024),
                    file_path,
                )

            file_size = os.path.getsize(file_path)
            log_id = self._log_crear({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': file_path,
                'url_origen': self.syscom_url_csv,
                'categorias_importadas': self.categorias_importar or '----',
                'tipo_accion': 'Descarga CSV',
                'tasa_cambio': 0.0,
            })

            if var._logger_info:
                _logger.info(f"Syscom: Registro creado en bitácora con ID {log_id} para la descarga realizada.")

            return file_path
        except requests.RequestException as e:
            _logger.error(f"Error en descarga: {e}", exc_info=True)
            # Si existe un archivo previo válido, retornarlo para reutilización
            try:
                if previous_log and previous_log.ruta_archivo and os.path.exists(previous_log.ruta_archivo):
                    _logger.warning('Fallo la descarga; se devolverá el archivo previo desde la bitácora para su reutilización.')
                    return previous_log.ruta_archivo
            except Exception:
                _logger.exception('Error al obtener archivo previo desde la bitácora')
            raise UserError(f'Error al descargar el archivo CSV: {str(e)}')
        except Exception as e:
            _logger.error(f"Error inesperado en descarga: {e}", exc_info=True)
            # En caso de error inesperado, intentar retornar archivo previo si existe
            try:
                if previous_log and previous_log.ruta_archivo and os.path.exists(previous_log.ruta_archivo):
                    _logger.warning('Error inesperado; se devolverá el archivo previo desde la bitácora para su reutilización.')
                    return previous_log.ruta_archivo
            except Exception:
                _logger.exception('Error al obtener archivo previo desde la bitácora')
            raise UserError(f'Error inesperado al descargar el archivo CSV: {str(e)}')

    def _limpiar_archivos_antiguos(self, archivo_actual):
        """Elimina archivos CSV descargados antiguos, manteniendo solo el actual."""
        try:
            directorio_descarga = var._ruta_descarga
            if var._logger_info:
                _logger.info('Limpiando archivos antiguos en el directorio de descargas...')
            for nombre_archivo in os.listdir(directorio_descarga):
                ruta_archivo = os.path.join(directorio_descarga, nombre_archivo)
                # BUG-31: condición anterior era `ruta_bak == archivo_actual`
                # (ruta_archivo+"_bak" == archivo_actual), que nunca era verdadera
                # si archivo_actual no es un _bak. La condición correcta protege
                # tanto el archivo actual como su respaldo generado por _csv_limpiar.
                if ruta_archivo == archivo_actual or \
                   ruta_archivo == archivo_actual + "_bak":
                    continue
                es_csv_syscom = (
                    nombre_archivo.startswith('syscom_products_')
                    and (nombre_archivo.endswith('.csv') or nombre_archivo.endswith('.csv_bak'))
                )
                if es_csv_syscom:
                    try:
                        os.remove(ruta_archivo)
                        if var._logger_info:
                            _logger.info(f'Removido archivo de descarga antiguo: {ruta_archivo}')
                    except Exception as e:
                        _logger.warning(f'No se pudo eliminar archivo antiguo {ruta_archivo}: {e}')
        except Exception:
            _logger.exception('Error al limpiar archivos antiguos en el directorio de descargas')

    def _csv_limpiar(self, ruta_csv_inicial='', mantener_respaldo=False) -> str:
        """Limpia el archivo CSV descargado, normalizándolo a UTF-8 y
        asegurando su formato. Mantiene un respaldo del original si se indica.
        Parametros:
            ruta_csv_inicial (str): Ruta del archivo CSV a limpiar.
            mantener_respaldo (bool): Si se debe mantener un respaldo del archivo original.
        Retorna:
            str: Ruta del archivo respaldo.
        """
        if not ruta_csv_inicial:
            raise ValueError('_csv_limpiar requiere una ruta de archivo válida.')
        ruta_csv_salida = ruta_csv_inicial + ".tmp"
        ruta_csv_respaldo = ruta_csv_inicial + "_bak"

        if var._logger_info:
            _logger.info(f"Limpiando archivo Syscom: {ruta_csv_inicial}")

        # Paso 1: Normalizar el archivo CSV utilizando la función normaliza_csv
        try:
            normaliza_csv(ruta_csv_inicial, ruta_csv_salida)
            # Paso 2: Swapping de archivos
            # MEJORA-37: mantener_respaldo ahora condiciona la creación del _bak;
            # antes siempre se creaba ignorando el parámetro.
            if mantener_respaldo:
                shutil.copy(ruta_csv_inicial, ruta_csv_respaldo)
            shutil.move(ruta_csv_salida, ruta_csv_inicial)

            # Paso 3: Log en Odoo
            file_size = os.path.getsize(ruta_csv_inicial)
            self._log_crear({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': ruta_csv_inicial,
                'url_origen': ruta_csv_inicial,
                'tipo_accion': 'Limpieza CSV',
                'categorias_importadas': '----',
                'tasa_cambio': 0.0,
            })

            return ruta_csv_respaldo if mantener_respaldo else ''

        except Exception as e:
            raise UserError(f'Error fatal al limpiar CSV, funcion csv_limpiar_pd: {str(e)}')

    def _procesar_csv(self, ruta_archivo_csv) -> None:
        """Procesar el archivo CSV e importar productos.
        Parametros:
            ruta_archivo (str): Ruta del archivo CSV a procesar.
        """
        categorias_filtro = []
        self.ensure_one()
        if var._logger_info:
            _logger.info(f'Inicia procesado de CSV, desde archivo: {ruta_archivo_csv}')

        if self.categorias_importar:
            categorias_filtro = [
                cat.strip().strip('"').strip("'")
                for cat in self.categorias_importar.split(',')
            ]

        # 1. Buscar o Crear el Proveedor (Partner)
        datos_proveedor = self.env['res.partner'].search([
            ('name', 'ilike', var._proveedor_nombre),
            ('supplier_rank', '>', 0)
        ], limit=1)

        if not datos_proveedor:
            # Opcional: Crear el proveedor si no existe
            datos_proveedor = self.env['res.partner'].create(
                [{
                    'name': var._proveedor_nombre,
                    'supplier_rank': 1,
                }]
            )
            self._registrar_log(descripcion=f"Proveedor {var._proveedor_nombre} "
                               f"creado con ID {datos_proveedor.id} "
                               f"para importación Syscom.",
                               tipo_operacion='Creación de Proveedor')
        else:
            self._registrar_log(descripcion=f"Proveedor {var._proveedor_nombre} "
                               f"encontrado con ID {datos_proveedor.id} "
                               f"para importación Syscom.",
                               tipo_operacion='Proveedor Existente')

        try:
            (
                datos_syscom_product,
                datos_syscom_proveedor,
                tipo_cambio_csv,
                codigos_procesados,
            ) = self._leer_csv(ruta_archivo_csv, categorias_filtro, datos_proveedor.id)

            (
                d_productos_actualizar,
                l_productos_crear_vals,
                productos_procesados,
            ) = self._clasificar_syscom_product(datos_syscom_product, codigos_procesados)

            #productos_actualizados = self._actualizar_productos_individual(d_productos_actualizar)
            productos_actualizados = self._actualizar_productos_sql_batch(d_productos_actualizar)

            productos_creados = self._procesar_batch_creacion(l_productos_crear_vals)

            (
                d_prod_syscom_actualizar,
                l_prod_syscom_crear_vals,
                prod_syscom_procesados,
            ) = self._clasificar_syscom_provider(datos_syscom_proveedor, codigos_procesados)

            # MEJORA-36: reemplazado actualización individual por SQL batch (equivalente al de product.template)
            provider_actualizados = self._actualizar_syscom_provider_sql_batch(d_prod_syscom_actualizar)
            provider_creados = self._procesar_batch_creacion_syscom_provider(l_prod_syscom_crear_vals)

            productos_registrados = self._procesar_info_proveedor(
                l_productos_crear_vals, d_productos_actualizar, datos_proveedor
            )
            self._registrar_log_importacion(
                ruta_archivo_csv, tipo_cambio_csv,
                productos_procesados, productos_creados, productos_actualizados,
            )
        except Exception as e:
            _logger.error(f'Error procesando CSV: {str(e)}')
            raise UserError(f'Error al procesar el archivo CSV: {str(e)}')

    def _leer_csv(self, ruta_archivo, categorias_filtro, syscom_provider_id) -> tuple:
        """Lee el archivo CSV y extrae los datos necesarios para la importación.
        Returns:
            tuple: Una tupla con las filas de datos, el tipo de cambio y los códigos a procesar.
        """
        datos_syscom_product = []
        datos_syscom_provider = []
        tipo_cambio_csv = None
        lista_codigos_procesados = []
        marca_cache = {}  # Cache para marcas ya procesadas
        contador_de_lineas_csv = 0
        contador_de_procesados = 0
        # MEJORA-43: verificar disponibilidad de product.brand una sola vez
        brand_disponible = "product.brand" in self.env.registry
        if not brand_disponible:
            _logger.warning('El módulo product_brand no está instalado, no se asignará marca a los productos importados.')

        with open(ruta_archivo, 'r', encoding='utf-8-sig') as archivo_csv:
            lector_csv = csv.DictReader(archivo_csv)

            for fila_datos_csv in lector_csv:
                contador_de_lineas_csv += 1
                menu_nvl1 = fila_datos_csv.get('Menu Nvl 1', '').strip()

                if (categorias_filtro and menu_nvl1 not in categorias_filtro):
                    continue

                default_code = fila_datos_csv.get('Modelo', '').strip()
                name = fila_datos_csv.get('Título', '').strip()

                if not default_code or not name:
                    continue

                su_precio = fila_datos_csv.get('Su Precio', '0').strip()
                tipo_cambio_str = fila_datos_csv.get('Tipo de Cambio', '').strip()
                marca_nombre = fila_datos_csv.get('Marca', var._sin_marca_nombre).strip()
                marca_id = self._set_or_create_brand(marca_nombre, marca_cache) if brand_disponible else False

                if tipo_cambio_str and not tipo_cambio_csv:
                    try:
                        tipo_cambio_csv = round(float(tipo_cambio_str.replace(',', '')), 2)
                        if var._logger_info:
                            _logger.info('Tipo de Cambio detectado en CSV: %s', tipo_cambio_csv)
                    except Exception:
                        _logger.warning('No se pudo parsear Tipo de Cambio desde el CSV: %s', tipo_cambio_str)

                menu_nvl2 = fila_datos_csv.get('Menu Nvl 2', '').strip()
                menu_nvl3 = fila_datos_csv.get('Menu Nvl 3', '').strip()
                id_syscom = fila_datos_csv.get('ID Producto', '').strip()
                clave_producto = fila_datos_csv.get('Código Fiscal', '').strip()
                syscom_url = fila_datos_csv.get('Link SYSCOM', '').strip()
                syscom_url_imagen = fila_datos_csv.get('Imagen Principal', '').strip()
                syscom_inventory = fila_datos_csv.get('Existencias', '0').strip()
                precios = self._calcular_precios(su_precio, tipo_cambio_csv)

                if not precios:
                    _logger.warning(f'Precio inválido para producto {default_code}')
                    continue

                standard_price, list_price = precios
                list_categoria_path = [menu_nvl1, menu_nvl2, menu_nvl3]

                datos_syscom_product.append({
                    'default_code': default_code,
                    'name': name,
                    'standard_price': standard_price,
                    'list_price': list_price,
                    'categoria_path': list_categoria_path,
                    'objetoimp': var._id_objetoimp,
                    'cat_unidad_medida': var._id_cat_unidad_medida,
                    'clave_producto': clave_producto,
                    'syscom_url': syscom_url,
                    'syscom_url_imagen': syscom_url_imagen,
                    'product_brand_id': marca_id,
                })

                datos_syscom_provider.append({
                    'default_code': default_code,
                    'partner_id': syscom_provider_id,
                    'product_tmpl_id': None,  # Se asignará después de crear/actualizar el producto
                    'id_syscom': id_syscom,
                    'syscom_url': syscom_url,
                    'syscom_url_imagen': syscom_url_imagen,
                    'syscom_inventory': syscom_inventory,
                    # 'syscom_obsoleto': syscom_obsoleto,
                })

                lista_codigos_procesados.append(default_code)
                contador_de_procesados += 1

        if var._logger_info:
            _logger.info(f'CSV procesado completamente. Total filas procesadas: {contador_de_lineas_csv}, Productos a importar: {contador_de_procesados}')

        # MEJORA-45: deduplicar preservando orden (el CSV puede tener el mismo default_code dos veces)
        lista_codigos_procesados = list(dict.fromkeys(lista_codigos_procesados))

        resultados = (datos_syscom_product,
                      datos_syscom_provider,
                      tipo_cambio_csv,
                      lista_codigos_procesados)

        return resultados

    def _calcular_precios(self, su_precio, tipo_cambio_csv) -> tuple:
        """Calcula el precio estándar y el precio de venta.
        A partir del precio de compra (su_precio) y el tipo de cambio.
        Si la configuración indica que se deben convertir precios de
        USD a MXN, se aplica la tasa de cambio.
        Luego se calcula el precio de venta aplicando el porcentaje
        de ganancia.
        Returns:
            tuple: Una tupla con el precio estándar y el precio de
              venta.
        """
        try:
            price_raw = float(su_precio.replace(',', ''))
            actual_tasa_cambio = getattr(self, 'tasa_cambio', var._mxn_valor)
            if self.usd_a_mxn:
                tasa = tipo_cambio_csv if tipo_cambio_csv else (actual_tasa_cambio)
                standard_price = round(price_raw * tasa, 2)
            else:
                standard_price = round(price_raw, 2)
            list_price = round(standard_price * (1 + (self.ganancia_porcentaje / 100)), 2)
            return (standard_price, list_price)  # MEJORA-51
        except Exception:
            # BUG-29: antes retornaba (None, None) — una tupla no vacía es truthy,
            # por lo que el guard `if not precios:` en _leer_csv nunca la detectaba
            # y los None se propagaban a la BD. Retornar None permite que el guard funcione.
            return None

    def _set_or_create_brand(self, nombre_marca, marca_cache=None) -> int:
        """Busca o crea una marca en el modelo product.brand.
          y devuelve su ID.
          Args:
            nombre_marca (str): El nombre de la marca a buscar o crear.
            marca_cache (dict): Un diccionario para almacenar las marcas ya creadas.
          Returns:
            int: El ID de la marca encontrada o creada."""
        if marca_cache is None:
            marca_cache = {}
        marca_id = False
        if nombre_marca in marca_cache:
            return marca_cache[nombre_marca]
        marca_id = self.env['product.brand'].search(
            [('name', '=', nombre_marca)],
            limit=1)
        if not marca_id:
            marca_id = self.env['product.brand'].create([{
                'name': nombre_marca,
            }])
        marca_id = marca_id.id
        marca_cache[nombre_marca] = marca_id
        return marca_id

    def _clasificar_syscom_product(self, datos_syscom_product, codigos_a_procesar) -> tuple:
        """Clasifica los productos en dos grupos: los que se deben actualizar.
        y los que se deben crear.
        Para los productos a actualizar, se construye un diccionario con los
        IDs de producto y los valores a actualizar.
        Para los productos a crear, se construye una lista de diccionarios
        con los valores para crear cada producto.
        Returns:
            tuple: Una tupla con los diccionarios de productos a actualizar
              y a crear, y el número de productos procesados.
        """

        if var._logger_info:
            _logger.info('Clasificando productos para importación en product.template...')

        d_productos_actualizar = {}
        l_productos_crear_vals = []
        productos_procesados = 0
        productos_existentes = {}

        if codigos_a_procesar:
            productos_actuales = self.env['product.template'].search([
                ('default_code', 'in', codigos_a_procesar)
            ])
            productos_existentes = {p.default_code: p for p in productos_actuales}

        # MEJORA-40: detectar la categoría raíz de Odoo una sola vez antes del loop.
        # Sin esto, los niveles del CSV (ej. "Redes") se creaban como raíces huérfanas
        # paralelas a "Todos/All", desconectadas de la jerarquía estándar de Odoo.
        # La búsqueda por parent_id=False es agnóstica al idioma ("Todos" o "All").
        cat_raiz = self.env['product.category'].search([('parent_id', '=', False)], limit=1)
        cat_raiz_nombre = cat_raiz.name if cat_raiz else None
        if var._logger_info:
            _logger.info(
                'Categoría raíz detectada: %s (id=%s)',
                cat_raiz_nombre, cat_raiz.id if cat_raiz else 'N/A',
            )

        categoria_cache = {}
        for linea_datos in datos_syscom_product:
            default_code = linea_datos['default_code']

            # MEJORA-40: anteceder la raíz a la ruta del CSV para que las categorías
            # queden anidadas bajo "Todos/All" en lugar de crearse como raíces sueltas.
            # Si no se encontró raíz (cat_raiz_nombre=None), se usa la ruta original
            # como fallback para no romper el comportamiento previo.
            categoria_path = (
                [cat_raiz_nombre] + linea_datos['categoria_path']
                if cat_raiz_nombre else linea_datos['categoria_path']
            )
            categoria = self._get_or_create_category_from_parts(
                categoria_path, categoria_cache
            )
            if default_code in productos_existentes:
                product = productos_existentes[default_code]
                d_productos_actualizar[product.id] = {
                    'default_code': default_code,
                    'name': linea_datos['name'],
                    'standard_price': linea_datos['standard_price'],
                    'list_price': linea_datos['list_price'],
                    # MEJORA-38: categ_id incluido para mantener la categoría sincronizada
                    # con Syscom en cada importación (antes solo se asignaba al crear).
                    'categ_id': categoria.id if categoria else False,
                    # Estos deberian de ser campos personalizados en el modelo
                    #  supplierinfo o en un modelo relacionado, no en
                    # product.template directamente, ajustar según corresponda
                    'product_url_ref': linea_datos.get('syscom_url'),
                    'product_url_image': linea_datos.get('syscom_url_imagen'),
                    'product_brand_id': linea_datos.get('product_brand_id'),
                }
            else:
                l_productos_crear_vals.append({
                    'name': linea_datos['name'],
                    'default_code': default_code,
                    'description_sale': linea_datos['name'],
                    'standard_price': linea_datos['standard_price'],
                    'list_price': linea_datos['list_price'],
                    'categ_id': categoria.id if categoria else False,
                    'type': 'consu',
                    'purchase_ok': True,
                    'sale_ok': True,
                    'cat_unidad_medida': linea_datos['cat_unidad_medida'],
                    'clave_producto': linea_datos['clave_producto'],
                    'objetoimp': linea_datos['objetoimp'],
                    'product_url_ref': linea_datos.get('syscom_url'),
                    'product_url_image': linea_datos.get('syscom_url_imagen'),
                    'product_brand_id': linea_datos.get('product_brand_id'),
                })
            productos_procesados += 1
        return d_productos_actualizar, l_productos_crear_vals, productos_procesados

    def _clasificar_syscom_provider(self, datos_syscom_proveedor=None, codigos_a_procesar=None) -> tuple:
        """Clasifica registros de proveedor Syscom en dos grupos: actualizar y crear.
        Returns:
            tuple: (dict actualizar, list crear, int procesados)
        """
        if datos_syscom_proveedor is None:
            datos_syscom_proveedor = []

        if codigos_a_procesar is None:
            codigos_a_procesar = []

        if var._logger_info:
            _logger.info('Clasificando productos de proveedor syscom...')

        d_productos_actualizar = {}
        l_productos_crear_vals = []
        lista_DCode_IDSyscom = {}
        producto_template_default_code_id_map = {}
        contador_productos_procesados = 0
        contador_omitidos = 0
        productos_perdidos_duplicados = None


        # BUG-42: validación fuera del try para que el UserError no sea tragado
        # por el except Exception que envuelve el procesamiento.
        if not datos_syscom_proveedor:
            mensaje = 'No se proporcionaron datos de proveedor syscom para clasificar.'
            if var._logger_info:
                _logger.info(mensaje)
            raise UserError(mensaje)

        try:
            if datos_syscom_proveedor:
                #set_productos_provider_syscom = self.env['product.provider.syscom'].search([
                #    ('default_code', 'in', codigos_a_procesar)
                #])
                # MEJORA-34: antes era search([]) — cargaba TODA la tabla sin filtro,
                # lo que se vuelve muy costoso conforme crece el catálogo. Filtrar por
                # codigos_a_procesar limita la consulta a los códigos del CSV actual.
                # La detección de duplicados (lista_DCode_IDSyscom) sigue funcionando
                # dentro del subconjunto importado.
                set_productos_provider_syscom = self.env['product.provider.syscom'].search([
                    ('default_code', 'in', codigos_a_procesar)
                ])

                # Fix para detectar códigos duplicados en product.provider.syscom que podrían causar problemas de clasificación
                # debemos de cambiar la comparacion de default_code que en ocasiones puede ser duplicada en el csv,
                # ya que puede tratarse del mismo producto pero con un producto descatlogado o modelo distinto,
                # lo ideal sería tener un identificador único de producto en el csv para evitar esta situación, pero
                # mientras tanto, este fix nos ayudará a identificar posibles registros problemáticos.
                # modificamos para usar en lugar de default_code como clave, una tupla de (default_code, id_syscom)
                # para intentar evitar falsos positivos en la detección de duplicados, aunque esto dependerá de la
                # calidad de los datos en el csv.
                lista_DCode_IDSyscom = {(p.default_code, p.id_syscom): p for p in set_productos_provider_syscom}
                lista_productos_template = self.env['product.template'].search_read(
                    [
                        ('default_code', 'in', codigos_a_procesar)
                    ],
                    ['default_code',
                     'id'
                    ]
                )
                lista_ids_DCode_IDSyscom = {p.id for p in lista_DCode_IDSyscom.values()}
                productos_perdidos_duplicados = set_productos_provider_syscom.filtered(
                    lambda p: p.id not in lista_ids_DCode_IDSyscom
                    )

                if productos_perdidos_duplicados:
                    detalle = [(p.id, p.default_code, p.id_syscom) for p in productos_perdidos_duplicados]
                    _logger.warning(
                        'Se encontraron %d registros en product.provider.syscom con clave (default_code, id_syscom) duplicada: %s',
                        len(productos_perdidos_duplicados), detalle,
                    )
                    self._log_crear({
                        'fecha_descarga': fields.Datetime.now(),
                        'tamano_descarga': 'NA',
                        'ruta_archivo': 'NA',
                        'url_origen': 'NA',
                        'tipo_accion': 'Registros Perdidos/Duplicados',
                        'categorias_importadas': str(detalle),
                        'tasa_cambio': 0.0,
                    })

                producto_template_default_code_id_map = {p['default_code']: p['id'] for p in lista_productos_template}
                conteo_codigos_a_procesar = len(codigos_a_procesar)
                conteo_set_provider = len(set_productos_provider_syscom)
                conteo_default_code_provider = len(lista_DCode_IDSyscom)
                conteo_datos_syscom_proveedor = len(datos_syscom_proveedor)
                conteo_productos_template = len(lista_productos_template)
                lista_productos_existentes = list(lista_DCode_IDSyscom)[:10]

                if var._logger_info:
                    _logger.info(
                        'syscom_provider — codigos=%d provider_total=%d provider_unicos=%d datos_csv=%d template=%d',
                        conteo_codigos_a_procesar, conteo_set_provider,
                        conteo_default_code_provider, conteo_datos_syscom_proveedor,
                        conteo_productos_template,
                    )
                    _logger.info(f' productos_existentes: {lista_productos_existentes}.')
            for ldatos in datos_syscom_proveedor:
                default_code = ldatos['default_code']
                id_syscom = ldatos.get('id_syscom')
                clave = (default_code, id_syscom)
                try:
                    syscom_inventory = int(ldatos.get('syscom_inventory') or 0)
                except (ValueError, TypeError):
                    syscom_inventory = 0

                if clave in lista_DCode_IDSyscom:
                    product = lista_DCode_IDSyscom[clave]
                    d_productos_actualizar[product.id] = {
                        'syscom_inventory': syscom_inventory,
                        'syscom_url': ldatos.get('syscom_url'),
                        'syscom_url_imagen': ldatos.get('syscom_url_imagen'),
                    }
                else:
                    tmpl_id = producto_template_default_code_id_map.get(default_code)
                    if not tmpl_id:
                        _logger.warning(
                            'No se encontró product.template para default_code %s; '
                            'se omite el registro de proveedor syscom.', default_code)
                        contador_omitidos += 1
                        continue
                    l_productos_crear_vals.append({
                        'default_code': default_code,
                        'partner_id': ldatos['partner_id'],
                        'id_syscom': ldatos['id_syscom'],
                        'product_tmpl_id': tmpl_id,
                        'syscom_inventory': syscom_inventory,
                        'syscom_url': ldatos.get('syscom_url'),
                        'syscom_url_imagen': ldatos.get('syscom_url_imagen'),
                    })
                contador_productos_procesados += 1
        except Exception as e:
            _logger.error(f'Error al clasificar datos de proveedor Syscom: {e}', exc_info=True)

        if var._logger_info:
            _logger.info(
                'Clasificación syscom_provider completada: %d procesados, '
                '%d a actualizar, %d a crear, %d omitidos.',
                contador_productos_procesados, len(d_productos_actualizar),
                len(l_productos_crear_vals), contador_omitidos)
        return d_productos_actualizar, l_productos_crear_vals, contador_productos_procesados

    def _actualizar_productos_individual(self, productos_actualizar) -> int:
        """Actualiza productos existentes registro por registro.
        Args:
            productos_actualizar (dict): Diccionario con los IDs de producto y los valores a actualizar.
        Returns:
            int: El número de productos actualizados.
        """
        if not productos_actualizar:
            return 0

        total = len(productos_actualizar)
        inicio = datetime.now()

        def _elapsed():
            return (datetime.now() - inicio).total_seconds()

        if var._logger_info:
            _logger.info('productos_individual — inicio total=%d', total)

        count = 0
        for product_id, values in productos_actualizar.items():
            self.env['product.template'].browse(product_id).write(values)
            count += 1
            if var._logger_info and (count % var._registros_por_batch == 0 or count == total):
                _logger.info(
                    'productos_individual pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                    count / total * 100, count, total, _elapsed(),
                )
            if not var._usar_bitacora_precios:
                continue
            try:
                registrar_bitacora_precios(
                    f"Producto actualizado: {values['default_code']} - Nuevo precio: {values.get('list_price', 'N/A')}"
                )
            except Exception as e:
                _logger.error(f'Error al registrar bitácora de producto actualizado: {e}')

        if var._logger_info:
            _logger.info(
                'productos_individual — completado total=%d elapsed=%.1fs',
                total, _elapsed(),
            )
        return total

    def _actualizar_productos_sql_batch(self, productos_actualizar) -> int:
        """Actualiza productos existentes usando SQL batch para campos numéricos/char directos.

        Campos via SQL (no traducibles, no JSONB): list_price, product_url_ref,
            product_url_image, product_brand_id.
        Campos via ORM agrupado: name (JSONB traducible), standard_price (price.history).

        Args:
            productos_actualizar (dict): Diccionario {product_template_id: values}.
        Returns:
            int: El número de productos actualizados.
        Notes:
            - No soporta multi-variante: standard_price se actualiza en product.product por product_tmpl_id.
            - Pendiente migrar a multi-variante cuando se implemente.
        """
        if not productos_actualizar:
            return 0

        total = len(productos_actualizar)
        chunk_size = var._registros_por_batch
        inicio = datetime.now()

        def _elapsed():
            return (datetime.now() - inicio).total_seconds()

        if var._logger_info:
            _logger.info('sql_batch — inicio total=%d chunk_size=%d', total, chunk_size)

        try:
            # Fase 1: SQL batch en chunks — campos varchar/numeric directos en product_template
            # BUG-41: categ_id incluido en la tupla y en el SET para que MEJORA-38 tenga efecto
            rows_template = [
                (
                    vals['list_price'],
                    vals.get('product_url_ref'),
                    vals.get('product_url_image'),
                    vals.get('product_brand_id'),
                    vals.get('categ_id') or None,
                    product_id,
                )
                for product_id, vals in productos_actualizar.items()
            ]
            sql = """UPDATE product_template
                        SET list_price=%s, product_url_ref=%s,
                            product_url_image=%s, product_brand_id=%s,
                            categ_id=COALESCE(%s, categ_id)
                      WHERE id=%s"""
            procesados_sql = 0
            for i in range(0, total, chunk_size):
                chunk = rows_template[i:i + chunk_size]
                self.env.cr.executemany(sql, chunk)
                procesados_sql += len(chunk)
                if var._logger_info:
                    _logger.info(
                        'sql_batch fase=SQL pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                        procesados_sql / total * 100, procesados_sql, total, _elapsed(),
                    )

            # Fase 2: name — JSONB traducible, via ORM agrupado por valor
            grupos_nombre = {}
            for product_id, vals in productos_actualizar.items():
                nombre = vals.get('name')
                if nombre is not None:
                    grupos_nombre.setdefault(nombre, []).append(product_id)
            procesados_name = 0
            for nombre, ids in grupos_nombre.items():
                self.env['product.template'].browse(ids).write({'name': nombre})
                procesados_name += len(ids)
                if var._logger_info and (procesados_name % chunk_size == 0 or procesados_name == total):
                    _logger.info(
                        'sql_batch fase=name pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                        procesados_name / total * 100, procesados_name, total, _elapsed(),
                    )

            # Fase 3: standard_price — via ORM para mantener product.price.history
            grupos_precio = {}
            for product_id, vals in productos_actualizar.items():
                precio = vals.get('standard_price')
                if precio is not None:
                    grupos_precio.setdefault(precio, []).append(product_id)
            procesados_precio = 0
            for precio, ids in grupos_precio.items():
                self.env['product.template'].browse(ids).write({'standard_price': precio})
                procesados_precio += len(ids)
                if var._logger_info and (procesados_precio % chunk_size == 0 or procesados_precio == total):
                    _logger.info(
                        'sql_batch fase=standard_price pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                        procesados_precio / total * 100, procesados_precio, total, _elapsed(),
                    )

            # Invalidar caché del ORM
            ids = list(productos_actualizar.keys())
            self.env['product.template'].browse(ids).invalidate_recordset([
                'name', 'list_price', 'standard_price',
                'product_url_ref', 'product_url_image', 'product_brand_id',
            ])

            if var._logger_info:
                _logger.info(
                    'sql_batch — completado total=%d elapsed=%.1fs',
                    total, _elapsed(),
                )
        except Exception as e:
            _logger.error(
                'sql_batch — error elapsed=%.1fs: %s', _elapsed(), e, exc_info=True,
            )
            if var._logger_info:
                _logger.info('sql_batch — fallback a actualización individual')
            return self._actualizar_productos_individual(productos_actualizar)

        return total

    def _actualizar_syscom_provider_individual(self, productos_actualizar) -> int:
        """Actualiza registros de proveedor syscom registro por registro.
        Args:
            productos_actualizar (dict): Diccionario con los IDs de registro y los valores a actualizar.
        Returns:
            int: El número de registros actualizados.
        """
        if not productos_actualizar:
            return 0

        total = len(productos_actualizar)
        inicio = datetime.now()

        def _elapsed():
            return (datetime.now() - inicio).total_seconds()

        if var._logger_info:
            _logger.info('syscom_provider_individual — inicio total=%d', total)

        count = 0
        for record_id, values in productos_actualizar.items():
            self.env['product.provider.syscom'].browse(record_id).write(values)
            count += 1
            if var._logger_info and (count % var._registros_por_batch == 0 or count == total):
                _logger.info(
                    'syscom_provider_individual pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                    count / total * 100, count, total, _elapsed(),
                )

        if var._logger_info:
            _logger.info(
                'syscom_provider_individual — completado total=%d elapsed=%.1fs',
                total, _elapsed(),
            )
        return total

    def _actualizar_syscom_provider_sql_batch(self, productos_actualizar) -> int:
        """Actualiza product.provider.syscom usando SQL batch con fallback individual.
        MEJORA-35: equivalente a _actualizar_productos_sql_batch pero para el modelo
        de proveedor Syscom. Todos los campos son columnas directas (no JSONB ni
        price.history), por lo que un solo UPDATE por chunk es suficiente.
        Actualiza además last_update con la hora UTC de la ejecución.
        Args:
            productos_actualizar (dict): {record_id: {syscom_inventory, syscom_url, syscom_url_imagen}}
        Returns:
            int: Número de registros actualizados.
        """
        if not productos_actualizar:
            return 0

        total = len(productos_actualizar)
        chunk_size = var._registros_por_batch
        inicio = datetime.now()

        def _elapsed():
            return (datetime.now() - inicio).total_seconds()

        if var._logger_info:
            _logger.info('syscom_provider_sql_batch — inicio total=%d chunk_size=%d', total, chunk_size)

        try:
            ahora = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            rows = [
                (
                    vals['syscom_inventory'],
                    vals.get('syscom_url'),
                    vals.get('syscom_url_imagen'),
                    ahora,
                    record_id,
                )
                for record_id, vals in productos_actualizar.items()
            ]
            sql = """UPDATE product_provider_syscom
                        SET syscom_inventory=%s, syscom_url=%s,
                            syscom_url_imagen=%s, last_update=%s
                      WHERE id=%s"""
            procesados = 0
            for i in range(0, total, chunk_size):
                chunk = rows[i:i + chunk_size]
                self.env.cr.executemany(sql, chunk)
                procesados += len(chunk)
                if var._logger_info:
                    _logger.info(
                        'syscom_provider_sql_batch pct=%.1f%% registros=%d/%d elapsed=%.1fs',
                        procesados / total * 100, procesados, total, _elapsed(),
                    )
            ids = list(productos_actualizar.keys())
            self.env['product.provider.syscom'].browse(ids).invalidate_recordset([
                'syscom_inventory', 'syscom_url', 'syscom_url_imagen', 'last_update',
            ])
            if var._logger_info:
                _logger.info(
                    'syscom_provider_sql_batch — completado total=%d elapsed=%.1fs',
                    total, _elapsed(),
                )
        except Exception as e:
            _logger.error('syscom_provider_sql_batch — error: %s', e, exc_info=True)
            if var._logger_info:
                _logger.info('syscom_provider_sql_batch — fallback a actualización individual')
            return self._actualizar_syscom_provider_individual(productos_actualizar)
        return total

    def _procesar_batch_creacion(self, productos_crear_vals) -> int:
        """Procesa la creación de nuevos productos en batch.
        Args:
            productos_crear_vals (list): Lista de diccionarios con los valores para crear nuevos productos.
        Returns:
            int: El número de productos creados.
        """
        if var._logger_info:
            _logger.info('Iniciando creación en batch de nuevos productos...')
        productos_creados = 0
        product_template = self.env['product.template']
        if productos_crear_vals:

            batch_size = var._registros_por_batch
            if var._logger_info:
                _logger.info(f'Creando {len(productos_crear_vals)} productos en batches de {batch_size}...')
            for i in range(0, len(productos_crear_vals), batch_size):
                chunk = productos_crear_vals[i:i+batch_size]
                try:
                    created_chunk = self.env['product.template'].create(chunk)
                    product_template |= created_chunk
                    if not var._usar_bitacora_precios:
                        continue
                    for product in created_chunk:
                        registrar_bitacora_precios(f"Producto creado: {product.default_code} - Precio: {product.list_price}")
                except Exception as e:
                    _logger.error(f'Error creando batch de productos (offset {i}): {e}', exc_info=True)
                    if var._logger_info:
                        _logger.info(f'Intentando crear productos uno por uno para identificar errores...')
                    for vals in chunk:
                        try:
                            product = self.env['product.template'].create(vals)
                            product_template |= product
                            if not var._usar_bitacora_precios:
                                continue
                            registrar_bitacora_precios(f"Producto creado: {product.default_code} - Precio: {product.list_price}")
                        except Exception as e_individual:
                            _logger.error(f'Error creando producto {vals.get("default_code", "N/A")}: {e_individual}', exc_info=True)
                            if var._logger_info:
                                _logger.info(f'Valores del producto con error: {vals}')
            productos_creados = len(product_template)
            try:
                tax_iva_16 = self.env['account.tax'].search([('amount', '=', 16), ('type_tax_use', '=', 'sale')], limit=1)
                if tax_iva_16 and product_template:
                    product_template.write({'taxes_id': [(6, 0, [tax_iva_16.id])]})
                    if var._logger_info:
                        _logger.info(f'Impuesto IVA 16% asignado a {len(product_template)} productos creados')
            except Exception as e:
                _logger.exception('No se pudo asignar impuestos en batch a los productos creados: %s', e)
        return productos_creados

    def _procesar_batch_creacion_syscom_provider(self, productos_crear_vals) -> int:
        """Procesa la creación de nuevos registros de proveedor syscom en batch.
        Args:
            productos_crear_vals (list): Lista de diccionarios con los valores para crear nuevos registros de proveedor syscom.
        Returns:
            int: El número de registros de proveedor syscom creados.
        """
        if var._logger_info:
            _logger.info('Iniciando creación en batch de nuevos registros de proveedor syscom...')

        productos_creados = 0
        contador_omitidos_unique = 0
        contador_excepciones = 0
        if productos_crear_vals:
            batch_size = var._registros_por_batch

            if var._logger_info:
                _logger.info(f'Creando {len(productos_crear_vals)} registros de proveedor syscom en batches de {batch_size}...')

            for elemento in range(0, len(productos_crear_vals), batch_size):
                chunk = productos_crear_vals[elemento:elemento+batch_size]
                try:
                    with self.env.cr.savepoint():
                        created_chunk = self.env['product.provider.syscom'].create(chunk)
                        productos_creados += len(created_chunk)
                except UniqueViolation as excepcion_error:
                    contador_omitidos_unique += 1
                    _logger.warning(
                        'Duplicado omitido, se encontró un registro con clave (default_code, id_syscom) ' \
                        'duplicada en product.provider.syscom durante creación en batch.' \
                        'Se procede a tratar de crear los registros uno por uno para identificar los duplicados exactos. ' \
                    )
                    _logger.error(f'Error creando batch de proveedor syscom (offset {elemento}): {excepcion_error}', exc_info=True)
                    for valores in chunk:
                        try:
                            with self.env.cr.savepoint():
                                self.env['product.provider.syscom'].create(valores)
                                productos_creados += 1
                        except UniqueViolation:
                            contador_omitidos_unique += 1
                            _logger.warning(
                                'Duplicado omitido — id_syscom=%s partner_id=%s ya existe.',
                                valores.get('id_syscom'), valores.get('partner_id'),
                            )
                        except Exception as e_individual:
                            contador_excepciones += 1
                            _logger.error(
                                f'Error creando elemento product.product.syscom con default_code =  {valores.get("default_code", "N/A")}:  {e_individual}',
                                exc_info=True,
                            )
        if var._logger_info:
            _logger.info(f'Registros creados: {productos_creados}, Omitidos (duplicados): {contador_omitidos_unique}, Excepciones: {contador_excepciones}')
        return productos_creados

    def _log_crear(self, vals: dict):
        """Persiste un registro en syscom.log usando su propio cursor,
        garantizando que sobrevive a rollbacks de la transacción principal."""
        with self.env.registry.cursor() as new_cr:
            new_env = api.Environment(new_cr, self.env.uid, {})
            registros = new_env['syscom.log'].create([vals]).id
            return registros

    def _registrar_log(self, descripcion='Falta descripcion', tipo_operacion='Operacion no especificada'):
        try:
            self._log_crear({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': 'NA',
                'ruta_archivo': '----',
                'url_origen': self.syscom_url_csv,
                'categorias_importadas': descripcion,
                'tipo_accion': tipo_operacion,
                'tasa_cambio': 0.0,
            })
            if var._logger_info:
                _logger.info(f'Syscom: Log registrado - {tipo_operacion}: {descripcion}')
        except Exception as e:
            _logger.error(f'Error al registrar log: {str(e)}')

    def _procesar_info_proveedor(self, l_productos_creados_vals=None, d_productos_actualizados=None, proveedor_info=None):
        if l_productos_creados_vals is None:
            l_productos_creados_vals = []
        if d_productos_actualizados is None:
            d_productos_actualizados = {}
        registros_procesados = 0
        total_productos = len(l_productos_creados_vals) + len(d_productos_actualizados)
        productos_vals = l_productos_creados_vals + list(d_productos_actualizados.values())
        # Buscar todos los productos por default_code en una sola consulta
        default_codes = [p['default_code'] for p in productos_vals]
        productos = self.env['product.template'].search([('default_code', 'in', default_codes)])
        productos_dict = {p.default_code: p for p in productos}

        # Buscar supplierinfo existentes para este proveedor y estos productos
        supplierinfos = self.env['product.supplierinfo'].search([
            ('product_tmpl_id', 'in', productos.ids),
            ('partner_id', '=', proveedor_info.id)
        ])
        supplierinfo_dict = {(s.product_tmpl_id.id, s.partner_id.id): s for s in supplierinfos}

        for producto_vals in productos_vals:
            try:
                producto_info = productos_dict.get(producto_vals['default_code'])
                if not producto_info:
                    _logger.warning(f'No se encontró el producto recién creado para info de proveedor: {producto_vals["default_code"]}')
                    continue

                key = (producto_info.id, proveedor_info.id)
                info_existente = supplierinfo_dict.get(key)

                precio = round(float(producto_vals['standard_price']), 2)
                if info_existente and info_existente.price == precio:
                    registros_procesados += 1
                    continue  # Si el precio es el mismo, no hacemos nada

                datos_tarifa = {
                    'partner_id': proveedor_info.id,
                    'product_tmpl_id': producto_info.id,
                    'price': precio,
                    'product_code': producto_vals['default_code'],
                    'product_name': producto_vals['name'],
                }

                if info_existente:
                    info_existente.write(datos_tarifa)
                else:
                    self.env['product.supplierinfo'].create(datos_tarifa)
                registros_procesados += 1
                if registros_procesados % 100 == 0 or registros_procesados == total_productos:
                    porcentaje = (registros_procesados / total_productos * 100) if total_productos > 0 else 0
                    if var._logger_info:
                        _logger.info(f'Progreso de info proveedor Porcentaje: {porcentaje:.2f}%')
            except Exception as e:
                _logger.error(f'Error al crear info de proveedor para producto {producto_vals["default_code"]}: {e}')
        if var._logger_info:
            _logger.info(f'Información de proveedor procesada para {registros_procesados} productos.')
        self._registrar_log(descripcion=f'Información de proveedor procesada para {registros_procesados} productos.', tipo_operacion='Info Proveedor')
        return registros_procesados

    def _registrar_log_importacion(self, filepath, tipo_cambio_csv, productos_procesados, productos_creados, productos_actualizados):
        """Registra un log detallado de la importación, incluyendo estadísticas y la tasa de cambio utilizada."""
        if var._logger_info:
            _logger.info(f'Importación completada: {productos_procesados} procesados, '
                         f'{productos_creados} creados, {productos_actualizados} actualizados')
        try:
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            categorias_importadas = self.categorias_importar or '----'
            tasa_log = tipo_cambio_csv if tipo_cambio_csv else (getattr(self, 'tasa_cambio', None) or 0.0)
            self._log_crear({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': filepath,
                'url_origen': self.syscom_url_csv,
                'categorias_importadas': categorias_importadas,
                'tipo_accion': 'Procesar CSV',
                'tasa_cambio': tasa_log,
            })
            if var._logger_info:
                _logger.info(f'Syscom: Tasa de cambio registrada en bitácora: {tasa_log}')
        except Exception:
            _logger.exception('No se pudo registrar la tasa de cambio en la bitácora')

    def _get_or_create_category_from_parts(self, lst_categorias, categoria_cache=None):
        """Obtener o crear categoría desde lista de partes ya separadas.
        categoria_cache: dict {(nombre, parent_id) -> recordset} compartido entre llamadas
        para evitar N+1 queries cuando se procesan múltiples productos.
        """
        if categoria_cache is None:
            categoria_cache = {}
        categoria_id = False
        parent_id = False

        if not lst_categorias:
            return categoria_id

        lista_filtrada = [p.strip() for p in lst_categorias if p and p.strip()]
        if not lista_filtrada:
            return categoria_id
        for categoria_nombre in lista_filtrada:
            cache_key = (categoria_nombre, parent_id)
            if cache_key in categoria_cache:
                categoria_id = categoria_cache[cache_key]
            else:
                categoria_id = self.env['product.category'].search([
                    ('name', '=', categoria_nombre),
                    ('parent_id', '=', parent_id)
                ], limit=1)
                if not categoria_id:
                    categoria_id = self.env['product.category'].create([{
                        'name': categoria_nombre,
                        'parent_id': parent_id,
                    }])
                categoria_cache[cache_key] = categoria_id
            parent_id = categoria_id.id
        return categoria_id

    @api.model
    def cron_importar_syscom(self):
        """Método llamado por el cron para importación automática"""
        config = self.get_config()
        config.ejecutar_importacion()

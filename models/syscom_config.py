
# ===========================
# models/syscom_config.py
# ===========================
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
from .csv_utilerias import  normaliza_csv
import requests
import csv
import os
import logging
import shutil

_logger = logging.getLogger(__name__)
_proveedor_nombre = "Syscom"  # Nombre del proveedor para asociar a los productos importados
_ruta_descarga = "/tmp/syscom_downloads"
_archivo_prueba = f"{_ruta_descarga}/verifica.txt"
_archivo_csv_prefijo = "syscom_products_"
_archivo_csv_extension = ".csv"
_archivo_bitacora_precios = f"{_ruta_descarga}/syscom_precios_bitacora.txt"
_usar_bitacora_precios = True  # Variable para controlar el uso de la bitácora de precios
_elimiar_archivo_previo = True
_tiempo_espera_descarga = 300  # segundos
_periodo_actualizaciones = 5  # tiempo en segundos para mostrar progreso de descarga
_id_objetoimp = "02"  # variable global para asignar el id del objeto de impuesto a los productos importados
_id_cat_unidad_medida = 1  # variable global para asignar la categoría de unidad de medida a los productos importados
_categoria_separador = ' \ '  # Separador para construir la ruta de categorías anidadas
_registros_por_batch = 5000  # cantidad de registros a procesar por batch en la creación de productos_
_mxn_valor = 1.0  # Valor de respaldo para convertir USD a MXN si no se encuentra en el CSV o en la configuración
_digitos_redondeo = 2  # Cantidad de dígitos para redondear la tasa de cambio al actualizarla desde el CSV o al calcular precios
_sin_marca_nombre = "S/M"  # Nombre de marca por defecto para productos sin marca especificada

# Funcion de bitacora a archivo de texto (opcional, se puede usar solo el modelo syscom.log para registrar eventos)
def registrar_bitacora_precios(mensaje):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(_ruta_descarga, exist_ok=True)
        with open(_archivo_bitacora_precios, 'a') as f:
            f.write(f'[{timestamp}] {mensaje}\n')
    except Exception as e:
        _logger.error(f'Error al registrar en bitácora de precios: {str(e)}')


class SyscomConfig(models.Model):
    _name = 'syscom.config'
    _description = 'Configuración de Syscom'
    _rec_name = 'syscom_url'

    syscom_url = fields.Char(
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
            _logger.info('Iniciando importación manual desde Syscom')
            periodo_segundos = self.get_config().periodo_segundos
            diferencia = 3600  # Valor inicial alto
            path_archivo_previo = ""
            reutilizar_archivo = False
            no_usado = None

            _logger.info("Syscom: Verificando última descarga en bitácora...")

            # 2. Verificar última descarga en bitácora
            last_log = self.env['syscom.log'].search(
                [('tipo_accion', '=', 'Descarga CSV')],
                limit=1,
                order='fecha_descarga desc')
            now = datetime.now()

            path_archivo_previo = last_log.ruta_archivo if last_log else ""

            if last_log and last_log.fecha_descarga and last_log.ruta_archivo:
                # Calcular diferencia de tiempo
                diferencia = (now - last_log.fecha_descarga).total_seconds()
            else:
                _logger.info("Syscom: No se encontraron registros previos de descarga en la bitácora.")
                diferencia = periodo_segundos + 1  # Forzar descarga si no hay registros

            _logger.info("Syscom: Última descarga fue hace %ss", int(diferencia))

            if diferencia < periodo_segundos:
                if os.path.exists(last_log.ruta_archivo):
                    _logger.info("Syscom: El tiempo transcurrido (%ss) es menor al periodo (%ss). Reutilizando archivo anterior.", int(diferencia), periodo_segundos)
                    reutilizar_archivo = True
                    path_archivo_previo = last_log.ruta_archivo
                    log_record = last_log # Usaremos el mismo registro para actualizar conteo si es necesario o uno nuevo
                else:
                    _logger.warning("Syscom: Ruta del archivo anterior no encontrada: %s. Se procederá a descargar un nuevo archivo.", last_log.ruta_archivo)
                    reutilizar_archivo = False
            else:
                _logger.info("Syscom: El tiempo transcurrido (%ss) es mayor al periodo (%ss). Se procederá a descargar un nuevo archivo.", int(diferencia), periodo_segundos)
                reutilizar_archivo = False

            # 3. Descarga o Reutilización
            if reutilizar_archivo:
                # Si reutilizamos, simplemente procesamos
                _logger.info("Syscom: Reutilizando archivo descargado previamente: %s", path_archivo_previo)
                archivo_path = path_archivo_previo
                _elimiar_archivo_previo = False  # No eliminaremos el archivo previo si lo estamos reutilizando
            else:
                # Proceder con la descarga normal
                _logger.info("Syscom: Iniciando nueva descarga del archivo CSV...")
                archivo_path = self._descargar_csv()
                _elimiar_archivo_previo = True  # Si descargamos un nuevo archivo, sí eliminaremos el previo después de procesar
                _logger.info("Syscom: Archivo descargado en: %s", archivo_path)

            if archivo_path == "NoCSV":
                _logger.error("Syscom: El archivo descargado no es un CSV válido. Verifique la URL y el acceso al recurso.")
                _elimiar_archivo_previo = False  # No eliminaremos el archivo previo si el nuevo no es válido
                raise ValueError("No se descargo el csv correctamente.")

            archivo_path, no_usado = self.csv_limpiar(archivo_path, mantener_respaldo=True)

            _logger.info("Syscom: Procesando el archivo CSV: %s", archivo_path)

            self._procesar_csv(archivo_path)

            # Si procesamos sin errores, limpiar archivos antiguos descargados
            self._limpiar_archivos_antiguos(archivo_path)

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
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/csv,application/csv,text/plain,*/*',
                'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
                'Connection': 'keep-alive',
            }
            # Configurar sesión y URL (tu código actual)
            # ...

            _logger.info(f"Descargando CSV desde: {self.syscom_url[:100]}...")

            # Buscar última descarga válida en la bitácora para usar como respaldo
            previous_log = self.env['syscom.log'].search([
                ('tipo_accion', '=', 'Descarga CSV')
            ], limit=1, order='fecha_descarga desc')

            previous_file = None
            if previous_log and previous_log.ruta_archivo and os.path.exists(previous_log.ruta_archivo):
                previous_file = previous_log.ruta_archivo
                _logger.info(f"Syscom: Archivo previo disponible para respaldo: {previous_file}")

            # actualizar la propiedad tipo de tasa de cambio con la presente en currency "base.USD"
            self.get_config().tasa_cambio = round((_mxn_valor /
                                                   self.env.ref('base.USD').rate),
                                                  _digitos_redondeo)
            # Iniciar tiempo de descarga
            start_time = datetime.now()
            last_print_time = start_time
            last_print_size = 0
            total_size = 0
            lista_categorias_importadas = ''

            # Para mostrar en consola/registro
            def print_progress(current_size, total_size=None):
                nonlocal last_print_time, last_print_size

                current_time = datetime.now()
                elapsed = (current_time - start_time).total_seconds()

                # Calcular velocidad (bytes/segundo)
                if elapsed > 0:
                    speed_bps = current_size / elapsed
                    speed_mbps = speed_bps / (1024 * 1024)
                else:
                    speed_mbps = 0

                # Calcular porcentaje si tenemos tamaño total
                if total_size:
                    percent = (current_size / total_size) * 100
                    progress_msg = f"{percent:.1f}%"
                else:
                    progress_msg = f"{current_size / (1024*1024):.2f} MB"

                # Imprimir cada MB o cada 5 segundos
                should_print = (
                    (current_size - last_print_size) >= (1024 * 1024) or  # Cada MB
                    (current_time - last_print_time).total_seconds() >= _periodo_actualizaciones
                )

                if should_print:
                    _logger.info(
                        f"Descargando: {progress_msg} | "
                        f"Velocidad: {speed_mbps:.2f} MB/s | "
                        f"Tiempo: {elapsed:.0f}s"
                    )
                    last_print_time = current_time
                    last_print_size = current_size

            # Descargar con stream
            response = requests.get(
                self.syscom_url,
                headers=headers,
                timeout=300,  # 5 minutos máximo
                stream=True,
                allow_redirects=True
            )

            response.raise_for_status()

            # obtener el tipo de contenido
            content_type = response.headers.get('Content-Type', '')

            # Obtener tamaño total si está disponible
            total_size = int(response.headers.get('content-length', 0))

            if total_size:
                _logger.info(f"Tamaño total del archivo: {total_size / (1024*1024):.2f} MB")

            if 'text/html' in content_type:
                _logger.error(
                    "Syscom Error: El servidor devolvió HTML (posible bloqueo o página de login).")
                if previous_file:
                    _logger.warning('Respuesta HTML recibida; se utilizará el archivo previo registrado como respaldo.')
                    return previous_file
                return "NoCSV"

            # Crear directorio
            download_dir = _ruta_descarga
            os.makedirs(download_dir, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{_archivo_csv_prefijo}{timestamp}{_archivo_csv_extension}'
            file_path = os.path.join(download_dir, filename)

            # Descargar por chunks con progreso
            downloaded = 0
            chunk_size = 8192  # 8KB chunks

            _logger.info("🚀 Iniciando descarga...")

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Mostrar progreso
                        print_progress(downloaded, total_size)

            # Mensaje final
            end_time = datetime.now()
            total_elapsed = (end_time - start_time).total_seconds()
            avg_speed = downloaded / total_elapsed if total_elapsed > 0 else 0

            _logger.info(f"""
            DESCARGA COMPLETADA:
            - Archivo: {filename}
            - Tamaño: {downloaded / (1024*1024):.2f} MB
            - Tiempo total: {total_elapsed:.1f} segundos
            - Velocidad promedio: {avg_speed / (1024*1024):.2f} MB/s
            - Ruta: {file_path}
            """)
            _logger.info("Syscom: Registro en bitacora.")

            # Registrar en bitácora
            file_size = os.path.getsize(file_path)
            lista_categorias_importadas = self.get_config().categorias_importar
            resultado = self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': file_path,
                'url_origen': self.syscom_url,
                'categorias_importadas': lista_categorias_importadas,
                'tipo_accion': 'Descarga CSV',
                'tasa_cambio': "0.0",  # Se actualizará con la tasa real al procesar el CSV, si se encuentra en él
            })

            _logger.info(f"Syscom: Registro creado en bitácora con ID {resultado.id} para la descarga realizada.")

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
            download_dir = _ruta_descarga
            _logger.info(f'Limpiando archivos antiguos en el directorio de descargas...')
            for nombre_archivo in os.listdir(download_dir):
                ruta_archivo = os.path.join(download_dir, nombre_archivo)
                ruta_bak = ruta_archivo + "_bak"
                if ruta_archivo == archivo_actual or \
                   ruta_bak == archivo_actual:
                    continue
                # Solo eliminar archivos que coincidan con el patrón de descargas de syscom
                if nombre_archivo.startswith('syscom_products_') and nombre_archivo.endswith('.csv') or \
                   nombre_archivo.startswith('syscom_products_') and nombre_archivo.endswith('.csv_bak'):
                    try:
                        os.remove(ruta_archivo)
                        _logger.info(f'Removido archivo de descarga antiguo: {ruta_archivo}')
                    except Exception as e:
                        _logger.warning(f'No se pudo eliminar archivo antiguo {ruta_archivo}: {e}')
        except Exception:
            _logger.exception('Error al limpiar archivos antiguos en el directorio de descargas')

    def csv_limpiar(self, ruta_csv_inicial='', mantener_respaldo=False):
        ruta_csv_inicial = ruta_csv_inicial or self._ruta_archivo_csv
        ruta_csv_salida = ruta_csv_inicial + ".tmp"
        ruta_csv_respaldo = ruta_csv_inicial + "_bak"

        _logger.info(f"Limpiando archivo Syscom: {ruta_csv_inicial}")

        # Paso 1: Normalizar el archivo CSV utilizando la función normaliza_csv
        try:
            normaliza_csv(ruta_csv_inicial, ruta_csv_salida)
            # Paso 2: Swapping de archivos
            shutil.copy(ruta_csv_inicial, ruta_csv_respaldo)
            shutil.move(ruta_csv_salida, ruta_csv_inicial)

            # Paso 3: Log en Odoo
            file_size = os.path.getsize(ruta_csv_inicial)
            self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': ruta_csv_inicial,
                'url_origen': ruta_csv_inicial,
                'tipo_accion': 'Limpieza Exitosa normalizando el archivo a utf8',
                'categorias_importadas': '----',
                'tasa_cambio': "0.0",
            })

            return ruta_csv_inicial, ruta_csv_respaldo

        except Exception as e:
            raise UserError(f'Error fatal al limpiar CSV, funcion csv_limpiar_pd: {str(e)}')

    def _crear_categorias(self, csv_path):
        """
        Crea categorías anidadas a partir de un CSV con columnas:
        'Menu Nvl 1', 'Menu Nvl 2', 'Menu Nvl 3'.
        """
        import csv
        categorias_creadas = 0
        # categorias_map = {}  # {(nvl1, nvl2, nvl3): id}
        with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                nvl1 = row.get('Menu Nvl 1', '').strip()
                nvl2 = row.get('Menu Nvl 2', '').strip()
                nvl3 = row.get('Menu Nvl 3', '').strip()
                parent_id = False
                # Nivel 1
                if nvl1:
                    cat1 = self.env['product.category'].search([
                        ('name', '=', nvl1), ('parent_id', '=', False)
                        ], limit=1)
                    if not cat1:
                        cat1 = self.env['product.category'].create({'name': nvl1, 'parent_id': False})
                        categorias_creadas += 1
                    parent_id = cat1.id
                # Nivel 2
                if nvl2:
                    cat2 = self.env['p_get_or_create_categoryroduct.category'].search([
                        ('name', '=', nvl2), ('parent_id', '=', parent_id)
                        ], limit=1)
                    if not cat2:
                        cat2 = self.env['product.category'].create({'name': nvl2, 'parent_id': parent_id})
                        categorias_creadas += 1
                    parent_id = cat2.id
                # Nivel 3
                if nvl3:
                    cat3 = self.env['product.category'].search([
                        ('name', '=', nvl3), ('parent_id', '=', parent_id)
                        ], limit=1)
                    if not cat3:
                        cat3 = self.env['product.category'].create({'name': nvl3, 'parent_id': parent_id})
                        categorias_creadas += 1
        _logger.info(f"Categorías creadas o existentes: {categorias_creadas}")
        return categorias_creadas


    def _procesar_csv(self, ruta_archivo):
        """Procesar el archivo CSV e importar productos"""
        self.ensure_one()
        categorias_filtro = []
        if self.categorias_importar:
            categorias_filtro = [
                cat.strip().strip('"').strip("'")
                for cat in self.categorias_importar.split(',')
            ]
        # 1. Buscar o Crear el Proveedor (Partner)
        datos_proveedor = self.env['res.partner'].search([
            ('name', 'ilike', _proveedor_nombre),
            ('supplier_rank', '>', 0)
        ], limit=1)

        if not datos_proveedor:
            # Opcional: Crear el proveedor si no existe
            datos_proveedor = self.env['res.partner'].create({
                'name': _proveedor_nombre,
                'supplier_rank': 1
            })
            self.registrar_log(descripcion=f"Proveedor '{_proveedor_nombre}' creado con ID {datos_proveedor.id} para importación Syscom.", tipo_operacion='Creación de Proveedor')
        else:
            self.registrar_log(descripcion=f"Proveedor '{_proveedor_nombre}' encontrado con ID {datos_proveedor.id} para importación Syscom.", tipo_operacion='Proveedor Existente')

        _logger.info(f'Iniciar procesado de CSV desde archivo: {ruta_archivo}')
        try:
            filas_de_datos, tipo_cambio_csv, codigos_procesar = self._leer_csv(ruta_archivo, categorias_filtro)
            d_productos_actualizar, l_productos_crear_vals, productos_procesados = self._clasificar_productos(filas_de_datos, codigos_procesar)
            productos_actualizados = self._procesar_batch_actualizacion(d_productos_actualizar)
            productos_creados = self._procesar_batch_creacion(l_productos_crear_vals)
            productos_registrados = self._procesar_info_proveedor(l_productos_crear_vals, d_productos_actualizar, datos_proveedor)
            self._registrar_log_importacion(ruta_archivo, tipo_cambio_csv, productos_procesados, productos_creados, productos_actualizados)
        except Exception as e:
            _logger.error(f'Error procesando CSV: {str(e)}')
            raise UserError(f'Error al procesar el archivo CSV: {str(e)}')

    def _leer_csv(self, ruta_archivo, categorias_filtro):
        filas_de_datos = []
        tipo_cambio_csv = None
        codigos_procesar = []
        with open(ruta_archivo, 'r', encoding='utf-8-sig') as archivo_csv:
            lector_csv = csv.DictReader(archivo_csv)
            for fila_datos_csv in lector_csv:
                if categorias_filtro:
                    menu_nvl1 = fila_datos_csv.get('Menu Nvl 1', '').strip()
                    if menu_nvl1 not in categorias_filtro:
                        continue
                default_code = fila_datos_csv.get('Modelo', '').strip()
                name = fila_datos_csv.get('Título', '').strip()
                su_precio = fila_datos_csv.get('Su Precio', '0').strip()
                tipo_cambio_str = fila_datos_csv.get('Tipo de Cambio', '').strip()
                marca_cache = {}  # Cache para marcas ya procesadas en este ciclo
                marca = fila_datos_csv.get('Marca', _sin_marca_nombre).strip()
                marca_id = self._set_or_create_brand(marca, marca_cache)
                marca_id = marca_id.id if marca_id else False
                if tipo_cambio_str and not tipo_cambio_csv:
                    try:
                        tipo_cambio_csv = round(float(tipo_cambio_str.replace(',', '')), 2)
                        _logger.info(f"Tipo de Cambio detectado en CSV: {tipo_cambio_csv}")
                    except Exception:
                        _logger.warning(f"No se pudo parsear 'Tipo de Cambio' desde el CSV: {tipo_cambio_str}")
                menu_nvl1 = fila_datos_csv.get('Menu Nvl 1', '').strip()
                menu_nvl2 = fila_datos_csv.get('Menu Nvl 2', '').strip()
                menu_nvl3 = fila_datos_csv.get('Menu Nvl 3', '').strip()
                clave_producto = fila_datos_csv.get('Código Fiscal', '').strip()
                link_syscom = fila_datos_csv.get('Link SYSCOM', '').strip()
                if not default_code or not name:
                    continue
                precios = self._calcular_precios(su_precio, tipo_cambio_csv)
                if not precios:
                    _logger.warning(f'Precio inválido para producto {default_code}')
                    continue
                standard_price, list_price = precios
                list_categoria_path = [menu_nvl1, menu_nvl2, menu_nvl3]
                filas_de_datos.append({
                    'default_code': default_code,
                    'name': name,
                    'standard_price': standard_price,
                    'list_price': list_price,
                    'categoria_path': list_categoria_path,
                    'objetoimp': _id_objetoimp,
                    'cat_unidad_medida': _id_cat_unidad_medida,
                    'clave_producto': clave_producto,
                    'syscom_url': link_syscom,
                    'product_brand_id': marca_id,
                })
                codigos_procesar.append(default_code)
        _logger.info(f'CSV parsing completed. Total rows collected for processing: {len(filas_de_datos)}')
        return filas_de_datos, tipo_cambio_csv, codigos_procesar

    def _calcular_precios(self, su_precio, tipo_cambio_csv):
        try:
            price_raw = float(su_precio.replace(',', ''))
            if self.usd_a_mxn:
                tasa = tipo_cambio_csv if tipo_cambio_csv else (getattr(self, 'tasa_cambio', 1.0) or 1.0)
                standard_price = round(price_raw * tasa, 2)
            else:
                standard_price = round(price_raw, 2)
            list_price = round(standard_price * (1 + (self.ganancia_porcentaje / 100)), 2)
            return standard_price, list_price
        except Exception:
            return None

    # Funcion para agregar la marca de los productos importados, usando el modulo de OCA product_brand, si esta instalado. Si no, se puede omitir o implementar de otra forma.
    def _set_or_create_brand(self, nombre_marca, marca_cache={}):
        if "product.brand" in self.env.registry:
            if nombre_marca in marca_cache:
                return marca_cache[nombre_marca]
            marca = self.env['product.brand'].search([('name', '=', nombre_marca)], limit=1)
            if not marca:
                marca = self.env['product.brand'].create({
                    'name': nombre_marca,
                })
            marca_cache[nombre_marca] = marca

            return marca
        else:
            _logger.warning('El módulo product_brand no está instalado, no se asignará marca a los productos importados.')
            return False

    def _clasificar_productos(self, filas_de_datos, codigos_procesar):
        d_productos_actualizar = {}
        l_productos_crear_vals = []
        productos_procesados = 0
        productos_existentes = {}
        if codigos_procesar:
            existing_products = self.env['product.template'].search([
                ('default_code', 'in', codigos_procesar)
            ])
            productos_existentes = {p.default_code: p for p in existing_products}
        for fila_con_datos in filas_de_datos:
            default_code = fila_con_datos['default_code']
            categoria = self._get_or_create_category_from_parts(fila_con_datos['categoria_path'])
            if default_code in productos_existentes:
                product = productos_existentes[default_code]
                d_productos_actualizar[product.id] = {
                    'default_code': default_code,
                    'name': fila_con_datos['name'],
                    'standard_price': fila_con_datos['standard_price'],
                    'list_price': fila_con_datos['list_price'],
                    # Estos deberian de ser campos personalizados en el modelo supplierinfo o en un modelo relacionado, no en product.template directamente, ajustar según corresponda
                    'syscom_url': fila_con_datos.get('syscom_url'),
                    'syscom_url_image': fila_con_datos.get('Imagen Principal'),  # Asumiendo que la URL de la imagen es la misma que la del producto, ajustar si es diferente
                    'product_brand_id': fila_con_datos.get('product_brand_id'),
                }
            else:
                l_productos_crear_vals.append({
                    'name': fila_con_datos['name'],
                    'default_code': default_code,
                    'description_sale': fila_con_datos['name'],
                    'standard_price': fila_con_datos['standard_price'],
                    'list_price': fila_con_datos['list_price'],
                    'categ_id': categoria.id if categoria else False,
                    'type': 'consu',
                    'purchase_ok': True,
                    'sale_ok': True,
                    'cat_unidad_medida': fila_con_datos['cat_unidad_medida'],
                    'clave_producto': fila_con_datos['clave_producto'],
                    'objetoimp': fila_con_datos['objetoimp'],
                    # Estos deberian de ser campos personalizados en el modelo supplierinfo o en un modelo relacionado, no en product.template directamente, ajustar según corresponda
                    'syscom_url': fila_con_datos.get('syscom_url'),
                    'syscom_url_image': fila_con_datos.get('Imagen Principal'),  # Asumiendo que la URL de la imagen es la misma que la del producto, ajustar si es diferente
                    'product_brand_id': fila_con_datos.get('product_brand_id'),
                })
            productos_procesados += 1
        return d_productos_actualizar, l_productos_crear_vals, productos_procesados

    def _procesar_batch_actualizacion(self, productos_actualizar):
        productos_actualizados = 0
        if productos_actualizar:
            _logger.info(f'Actualizando {len(productos_actualizar)} productos en batch...')
            # agregar un contador del porcentaje de actualización cada 100 registros procesados o cada 5 segundos, lo que ocurra primero
            total = len(productos_actualizar)
            count = 0
            for product_id, values in productos_actualizar.items():
                self.env['product.template'].browse(product_id).write(values)
                count += 1
                if count % 100 == 0 or count == total:
                    porcentaje = (count / total * 100) if total > 0 else 0
                    _logger.info(f'Progreso de actualización: {porcentaje:.2f}% ({count}/{total})')
                if (_usar_bitacora_precios is False):
                    continue
                try:
                    product = self.env['product.template'].browse(product_id)
                    registrar_bitacora_precios(f"Producto actualizado: {product.default_code} - Nuevo precio: {values.get('list_price', 'N/A')}")
                except Exception as e:
                    _logger.error(f'Error al registrar bitácora de producto actualizado: {e}')
            productos_actualizados = len(productos_actualizar)
        return productos_actualizados

    def _procesar_batch_creacion(self, productos_crear_vals):
        productos_creados = 0
        created_records = self.env['product.template']
        if productos_crear_vals:
            batch_size = _registros_por_batch
            _logger.info(f'Creando {len(productos_crear_vals)} productos en batches de {batch_size}...')
            for i in range(0, len(productos_crear_vals), batch_size):
                chunk = productos_crear_vals[i:i+batch_size]
                try:
                    created_chunk = self.env['product.template'].create(chunk)
                    created_records |= created_chunk
                    if (_usar_bitacora_precios is False):
                        continue
                    for product in created_chunk:
                        registrar_bitacora_precios(f"Producto creado: {product.default_code} - Precio: {product.list_price}")
                except Exception as e:
                    _logger.error(f'Error creando batch de productos (offset {i}): {e}', exc_info=True)
            productos_creados = len(created_records)
            try:
                tax_iva_16 = self.env['account.tax'].search([('amount', '=', 16), ('type_tax_use', '=', 'sale')], limit=1)
                if tax_iva_16 and created_records:
                    created_records.write({'taxes_id': [(6, 0, [tax_iva_16.id])]})
                    _logger.info(f'Impuesto IVA 16% asignado a {len(created_records)} productos creados')
            except Exception as e:
                _logger.exception('No se pudo asignar impuestos en batch a los productos creados: %s', e)
        return productos_creados

    # metodo para registrar una entrada al log recibiendo solo una descripcion y tipo de operacion,
    # usando datos adicionales como la fecha actual, url de syscom y categorias importadas desde la configuración actual
    def registrar_log(self, descripcion='Falta descripcion', tipo_operacion='Operacion no especificada'):
        try:
            self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': 'NA',
                'ruta_archivo': '----',
                'url_origen': self.syscom_url,
                'categorias_importadas': descripcion,
                'tipo_accion': tipo_operacion,
                'tasa_cambio': 0.0,
            })
            _logger.info(f'Syscom: Log registrado - {tipo_operacion}: {descripcion}')
        except Exception as e:
            _logger.error(f'Error al registrar log: {str(e)}')

    def _procesar_info_proveedor(self, l_productos_creados_vals=[], d_productos_actualizados={}, proveedor_info=None):
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
                    _logger.info(f'Progreso de info proveedor Porcentaje: {porcentaje:.2f}%')
            except Exception as e:
                _logger.error(f'Error al crear info de proveedor para producto {producto_vals["default_code"]}: {e}')
        _logger.info(f'Información de proveedor procesada para {registros_procesados} productos.')
        self.registrar_log(descripcion=f'Información de proveedor procesada para {registros_procesados} productos.', tipo_operacion='Info Proveedor')
        return registros_procesados

    def _registrar_log_importacion(self, filepath, tipo_cambio_csv, productos_procesados, productos_creados, productos_actualizados):
        _logger.info(f'Importación completada: {productos_procesados} procesados, '
                     f'{productos_creados} creados, {productos_actualizados} actualizados')
        try:
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            categorias_importadas = self.categorias_importar or '----'
            tasa_log = tipo_cambio_csv if tipo_cambio_csv else (getattr(self, 'tasa_cambio', None) or 0.0)
            self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': filepath,
                'url_origen': self.syscom_url,
                'categorias_importadas': categorias_importadas,
                'tipo_accion': 'Procesar CSV',
                'tasa_cambio': tasa_log,
            })
            _logger.info(f'Syscom: Tasa de cambio registrada en bitácora: {tasa_log}')
        except Exception:
            _logger.exception('No se pudo registrar la tasa de cambio en la bitácora')

    # metodo para modificar los modelos de impuestos en product.template, para asignar el impuesto de iva 16% a los productos importados
    # y el impuesto del 16% de iva en ventas
    def _asignar_impuestos(self, product_template):
        """Asignar impuestos a producto importado"""
        try:
            # Buscar el impuesto de IVA 16% (ajustar según tu configuración)
            tax_iva_16 = self.env['account.tax'].search([('amount', '=', 16), ('type_tax_use', '=', 'sale')], limit=1)
            if tax_iva_16:
                product_template.taxes_id = [(6, 0, [tax_iva_16.id])]
                _logger.info(f'Impuesto IVA 16% asignado al producto {product_template.default_code}')
            else:
                _logger.warning('No se encontró el impuesto de IVA 16% para asignar.')
        except Exception as e:
            _logger.error(f'Error al asignar impuestos: {str(e)}')
            raise UserError(f'Error al asignar impuestos al producto: {str(e)}')

    def _get_or_create_category_from_parts(self, parts_list):
        """Obtener o crear categoría desde lista de partes ya separadas

        Args:
            parts_list: Lista de strings con cada nivel ['Nivel1', 'Nivel2', 'Nivel3']

        Returns:
            Registro de product.category o None
        """
        if not parts_list:
            return None

        # Filtrar partes vacías
        parts = [p.strip() for p in parts_list if p and p.strip()]

        if not parts:
            return None

        parent_id = False
        categoria = None

        for part in parts:
            categoria = self.env['product.category'].search([
                ('name', '=', part),
                ('parent_id', '=', parent_id)
            ], limit=1)

            if not categoria:
                categoria = self.env['product.category'].create({
                    'name': part,
                    'parent_id': parent_id,
                })

            parent_id = categoria.id

        return categoria

    @api.model
    def cron_importar_syscom(self):
        """Método llamado por el cron para importación automática"""
        config = self.get_config()
        config.ejecutar_importacion()

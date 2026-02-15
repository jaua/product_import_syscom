# ===========================
# models/syscom_config.py
# ===========================
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import requests
import csv
import os
import logging
import shutil

_logger = logging.getLogger(__name__)
_ruta_descarga = "/tmp/syscom_downloads"
_archivo_prueba = f"{_ruta_descarga}/verifica.txt"
_elimiar_archivo_previo = True
_tiempo_espera_descarga = 300  # segundos
_periodo_actualizaciones = 5  # tiempo en segundos para mostrar progreso de descarga
_id_objetoimp = "02"  # variable global para asignar el id del objeto de impuesto a los productos importados
_id_cat_unidad_medida = 1  # variable global para asignar la categoría de unidad de medida a los productos importados
_registros_por_batch = 5000  # cantidad de registros a procesar por batch en la creación de productos_

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

            _logger.info("Syscom: Verificando última descarga en bitácora...")

            # 2. Verificar última descarga en bitácora
            last_log = self.env['syscom.log'].search([], limit=1, order='fecha_descarga desc')
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

            self.csv_limpiar(archivo_path, mantener_respaldo=True)

            _logger.info("Syscom: Procesando el archivo CSV: %s", archivo_path)

            self._procesar_csv(archivo_path)
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
            # Si procesamos sin errores, eliminar archivo previo si está configurado
            archivo_path = last_log.ruta_archivo
            if _elimiar_archivo_previo:
                try:
                    if os.path.exists(archivo_path):
                        os.remove(archivo_path)
                        _logger.info(f'Archivo temporal eliminado: {archivo_path}')
                except Exception as e:
                    _logger.warning(f'No se pudo eliminar el archivo temporal: {str(e)}')
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

            # Iniciar tiempo de descarga
            start_time = datetime.now()
            last_print_time = start_time
            last_print_size = 0
            total_size = 0
            categorias_importadas = ''

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
                        f"📥 Descargando: {progress_msg} | "
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
            filename = f'syscom_products_{timestamp}.csv'
            filepath = os.path.join(download_dir, filename)

            # Descargar por chunks con progreso
            downloaded = 0
            chunk_size = 8192  # 8KB chunks

            _logger.info("🚀 Iniciando descarga...")

            with open(filepath, 'wb') as f:
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
            ✅ DESCARGA COMPLETADA:
            - Archivo: {filename}
            - Tamaño: {downloaded / (1024*1024):.2f} MB
            - Tiempo total: {total_elapsed:.1f} segundos
            - Velocidad promedio: {avg_speed / (1024*1024):.2f} MB/s
            - Ruta: {filepath}
            """)
            _logger.info("Syscom: Registro en bitacora.")

            # Registrar en bitácora
            file_size = os.path.getsize(filepath)
            categorias_importadas = self.get_config().categorias_importar
            resultado = self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024):.2f} MB',
                'ruta_archivo': filepath,
                'url_origen': self.syscom_url,
                'categorias_importadas': categorias_importadas,
                'tipo_accion': 'Descarga CSV',
            })

            _logger.info(f"Syscom: Registro creado en bitácora con ID {resultado.id} para la descarga realizada.")

            # Mantener solo el archivo más reciente en el directorio de descargas.
            try:
                for fn in os.listdir(download_dir):
                    full = os.path.join(download_dir, fn)
                    if full == filepath:
                        continue
                    # Solo eliminar archivos que coincidan con el patrón de descargas de syscom
                    if fn.startswith('syscom_products_') and fn.endswith('.csv'):
                        try:
                            os.remove(full)
                            _logger.info(f'Removido archivo de descarga antiguo: {full}')
                        except Exception as e:
                            _logger.warning(f'No se pudo eliminar archivo antiguo {full}: {e}')
            except Exception:
                _logger.exception('Error al limpiar archivos antiguos en el directorio de descargas')

            return filepath
        except requests.RequestException as e:
            _logger.error(f"Error en descarga: {e}", exc_info=True)
            # Si existe un archivo previo válido, retornarlo para reutilización
            try:
                previous_log = self.env['syscom.log'].search([
                    ('tipo_accion', '=', 'Descarga CSV')
                ], limit=1, order='fecha_descarga desc')
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
                previous_log = self.env['syscom.log'].search([
                    ('tipo_accion', '=', 'Descarga CSV')
                ], limit=1, order='fecha_descarga desc')
                if previous_log and previous_log.ruta_archivo and os.path.exists(previous_log.ruta_archivo):
                    _logger.warning('Error inesperado; se devolverá el archivo previo desde la bitácora para su reutilización.')
                    return previous_log.ruta_archivo
            except Exception:
                _logger.exception('Error al obtener archivo previo desde la bitácora')

            raise UserError(f'Error inesperado al descargar el archivo CSV: {str(e)}')

    def csv_limpiar(self, csv_path: str = '', mantener_respaldo: bool = False):
        """Limpiar el archivo de las fallas en la codificacion.

        Debido a que algunos caracteres no siguen un
        estandar de contunuidad de los estadares UTF-8.
        Retorna un array con el path del archivo limpio y el archivo de
        respaldo.
        """
        if csv_path == "":
            csv_path = self._ruta_archivo_csv
        ruta_archivo_entrada = csv_path
        ruta_archivo_salida = csv_path + "_"
        ruta_archivo_respaldo = csv_path + "_bak"

        _logger.info(f"Limpiando archivo CSV: {ruta_archivo_entrada}")
        with open(ruta_archivo_entrada, 'rb') as archivo_entrada, \
             open(ruta_archivo_salida, 'w', encoding='utf-8') as archivo_salida:
            conteo_lineas = 0
            conteo_fallas = 0
            salta = False
            linea = "\n".encode("utf-8")
            while True:
                try:
                    if not salta:
                        linea = archivo_entrada.readline()
                    else:
                        salta = False
                    linea_limpia = linea.decode("utf-8")
                except UnicodeDecodeError as err:
                    _logger.warning(f"Caracter no decodificable encontrado en línea {conteo_lineas + 1}, eliminando carácter problemático.")
                    inicio = err.start
                    ln_temporal = linea
                    parte_inicial = ln_temporal[0:inicio - 1]
                    parte_secundaria = ln_temporal[inicio + 1:]
                    ln_temporal = parte_inicial + parte_secundaria
                    linea = ln_temporal
                    salta = True
                    conteo_fallas += 1
                    continue
                except Exception as e:
                    _logger.error(f"Error inesperado al limpiar línea {conteo_lineas + 1}: {str(e)}")
                    raise UserError(f'Error inesperado al limpiar el archivo CSV: {str(e)}')
                if not linea:
                    _logger.info("Fin del archivo alcanzado.")
                    break
                archivo_salida.write(linea_limpia)
                conteo_lineas += 1

        _logger.info(f"Archivo CSV corregido. Total de líneas procesadas: {conteo_lineas}")
        _logger.info(f"Total de caracteres problemáticos encontrados y eliminados: {conteo_fallas}")
        _logger.info(f"Respaldo del archivo original creado en: {ruta_archivo_respaldo}")

        try:
            _logger.info(f"Copiando archivo de entrada a respaldo: {ruta_archivo_entrada} -> {ruta_archivo_respaldo}")
            shutil.copy(ruta_archivo_entrada, ruta_archivo_respaldo)
            _logger.info(f"Reemplazando archivo original con el archivo limpio: {ruta_archivo_salida} -> {ruta_archivo_entrada}")
            shutil.move(ruta_archivo_salida, ruta_archivo_entrada)
        except Exception as e:
            _logger.error(f"Error al reemplazar el archivo original: {str(e)}")
            raise UserError(f'Error al limpiar el archivo CSV: {str(e)}')

        _logger.info(f"Registrando limpieza en bitacora.")
        file_size = os.path.getsize(ruta_archivo_entrada)

        resultado = self.env['syscom.log'].create({
                'fecha_descarga': fields.Datetime.now(),
                'tamano_descarga': f'{file_size / (1024 * 1024)} MB',
                'ruta_archivo': ruta_archivo_entrada,
                'url_origen': ruta_archivo_entrada,
                'categorias_importadas': '----',
                'tipo_accion': 'Limpiar archivo CSV',
            })

        _logger.info(f"Syscom: Registro creado en bitácora con ID {resultado.id} para la limpieza realizada.")

        return ruta_archivo_entrada, ruta_archivo_respaldo

    def _procesar_csv(self, filepath):
        """Procesar el archivo CSV e importar productos"""
        self.ensure_one()
        # Parsear lista de categorías
        categorias_filtro = []
        if self.categorias_importar:
            categorias_filtro = [
                cat.strip().strip('"').strip("'")
                for cat in self.categorias_importar.split(',')
            ]

        productos_procesados = 0
        productos_actualizados = 0
        productos_creados = 0

        # Listas para batch operations
        productos_actualizar = {}  # {product_id: values}
        productos_crear_vals = []
        codigos_procesar = []

        _logger.info(f'Starting CSV processing from file: {filepath}')
        try:
            # Primera pasada: recolectar datos del CSV
            rows_data = []
            with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
                csv_reader = csv.DictReader(csvfile)

                for csv_row in csv_reader:
                    # Filtrar por categoría si está configurado
                    if categorias_filtro:
                        menu_nvl1 = csv_row.get('Menu Nvl 1', '').strip()
                        if menu_nvl1 not in categorias_filtro:
                            continue

                    # Extraer datos del CSV
                    default_code = csv_row.get('Modelo', '').strip()
                    name = csv_row.get('Título', '').strip()
                    su_precio = csv_row.get('Su Precio', '0').strip()
                    menu_nvl1 = csv_row.get('Menu Nvl 1', '').strip()
                    menu_nvl2 = csv_row.get('Menu Nvl 2', '').strip()
                    menu_nvl3 = csv_row.get('Menu Nvl 3', '').strip()
                    clave_producto = csv_row.get('Código Fiscal', '').strip()

                    if not default_code or not name:
                        continue

                    # Calcular precios
                    try:
                        standard_price = float(su_precio.replace(',', ''))
                        list_price = standard_price * (1 + self.ganancia_porcentaje / 100)
                    except ValueError:
                        _logger.warning(f'Precio inválido para producto {default_code}')
                        continue

                    # Construir categoría
                    categoria_path = ' / '.join(filter(None, [menu_nvl1, menu_nvl2, menu_nvl3]))

                    rows_data.append({
                        'default_code': default_code,
                        'name': name,
                        'standard_price': standard_price,
                        'list_price': list_price,
                        'categoria_path': categoria_path,
                        'objetoimp': _id_objetoimp,
                        'cat_unidad_medida': _id_cat_unidad_medida,
                        'clave_producto': clave_producto,
                    })
                    codigos_procesar.append(default_code)

            _logger.info(f'CSV parsing completed. Total rows collected for processing: {len(rows_data)}')
            # Búsqueda batch de productos existentes
            productos_existentes = {}
            if codigos_procesar:
                existing_products = self.env['product.template'].search([
                    ('default_code', 'in', codigos_procesar)
                ])
                productos_existentes = {p.default_code: p for p in existing_products}

            # Procesar los datos recolectados
            for row_data in rows_data:
                default_code = row_data['default_code']
                categoria = self._get_or_create_category(row_data['categoria_path'])

                if default_code in productos_existentes:
                    # Producto existe - preparar para actualización
                    product = productos_existentes[default_code]
                    productos_actualizar[product.id] = {
                        'standard_price': row_data['standard_price'],
                        'list_price': row_data['list_price'],
                    }
                else:
                    # Producto nuevo - preparar para creación
                    productos_crear_vals.append({
                        'name': row_data['name'],
                        'default_code': default_code,
                        'description_sale': row_data['name'],
                        'standard_price': row_data['standard_price'],
                        'list_price': row_data['list_price'],
                        'categ_id': categoria.id if categoria else False,
                        'type': 'consu',
                        'purchase_ok': True,
                        'sale_ok': True,
                        'cat_unidad_medida': row_data['cat_unidad_medida'],
                        'clave_producto': row_data['clave_producto'],
                        'objetoimp': row_data['objetoimp'],
                    })

                productos_procesados += 1

            # Ejecutar operaciones batch
            # Actualizar productos existentes en batch
            if productos_actualizar:
                _logger.info(f'Actualizando {len(productos_actualizar)} productos en batch...')
                for product_id, values in productos_actualizar.items():
                    self.env['product.template'].browse(product_id).write(values)
                productos_actualizados = len(productos_actualizar)

            # Crear nuevos productos en batches (grupos de 5000)
            created_records = self.env['product.template']
            if productos_crear_vals:
                batch_size = _registros_por_batch
                _logger.info(f'Creando {len(productos_crear_vals)} productos en batches de {batch_size}...')
                for i in range(0, len(productos_crear_vals), batch_size):
                    chunk = productos_crear_vals[i:i+batch_size]
                    try:
                        created_chunk = self.env['product.template'].create(chunk)
                        created_records |= created_chunk
                        _logger.info(f'Batch de productos creado: {len(created_chunk)} productos (offset {i})')
                    except Exception as e:
                        _logger.error(f'Error creando batch de productos (offset {i}): {e}', exc_info=True)

                productos_creados = len(created_records)

                # Asignar impuestos en batch si se encuentra el impuesto IVA 16%
                try:
                    tax_iva_16 = self.env['account.tax'].search([('amount', '=', 16), ('type_tax_use', '=', 'sale')], limit=1)
                    if tax_iva_16 and created_records:
                        created_records.write({'taxes_id': [(6, 0, [tax_iva_16.id])]})
                        _logger.info(f'Impuesto IVA 16% asignado a {len(created_records)} productos creados')
                except Exception as e:
                    _logger.exception('No se pudo asignar impuestos en batch a los productos creados: %s', e)

            _logger.info(f'Importación completada: {productos_procesados} procesados, '
                         f'{productos_creados} creados, {productos_actualizados} actualizados')

        except Exception as e:
            _logger.error(f'Error procesando CSV: {str(e)}')
            raise UserError(f'Error al procesar el archivo CSV: {str(e)}')

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

    def _get_or_create_category(self, categoria_path):
        """Obtener o crear categoría de producto"""
        if not categoria_path:
            return None

        parts = [p.strip() for p in categoria_path.split('/')]
        parent_id = False

        for part in parts:
            if not part:
                continue

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

        return self.env['product.category'].browse(parent_id)

    @api.model
    def cron_importar_syscom(self):
        """Método llamado por el cron para importación automática"""
        config = self.get_config()
        config.ejecutar_importacion()

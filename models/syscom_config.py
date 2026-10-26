
# ===========================
# models/syscom_config.py
# ===========================
"""Configuración de la importación Syscom: solo los campos y el ciclo de
vida ligado directamente a ellos (recalcular el cron al cambiar
hora_ejecucion). El proceso de importación en sí (descarga, clasificación,
actualización/creación en batch, homologación de categorías, etc.) vive en
syscom_importador.py, que extiende este mismo modelo (_inherit) para que
ambos archivos sigan siendo un único modelo ORM: syscom.config.
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from .logging_utils import FuncNameFilter
from .syscom_parametros import SyscomParametros as Parametros
import csv
import difflib
import json
import logging

var = Parametros()
_logger = logging.getLogger(__name__)
_logger.addFilter(FuncNameFilter())

# Valores de "Menu Nvl 1" en el CSV que no son categorías reales (productos sin
# ficha completa); se excluyen del monitoreo de categorías.
_CATEGORIAS_PLACEHOLDER = {'', '---'}


def normalizar_categoria(nombre) -> str:
    """MEJORA-75: clave de comparación de categorías tolerante a cambios menores
    de Syscom (espacios dobles, mayúsculas). Debe coincidir con la normalización
    SQL de _despublicar_productos_ausentes: regexp_replace(lower(btrim(x)), '\\s+', ' ', 'g')."""
    return ' '.join((nombre or '').split()).lower()


def parsear_categorias(texto) -> list:
    """BUG-68: categorias_importar se partía con split(',') ignorando las comillas,
    por lo que "Herramientas, Ferretería y Material Eléctrico" se convertía en dos
    filtros que nunca coincidían. Se parsea como una línea CSV (respeta comillas
    dobles); los saltos de línea cuentan como separador."""
    if not texto:
        return []
    fila = next(csv.reader([texto.replace('\n', ',')], skipinitialspace=True), [])
    categorias = [c.strip().strip("'").strip() for c in fila]
    return [c for c in categorias if c]


# Nombre técnico del módulo — usado para consultar su versión instalada
# (ver _obtener_version_modulo). Único lugar donde vive este literal.
_NOMBRE_MODULO = 'product_import_syscom'


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
        help='Hora del día (UTC, formato 24h) para ejecutar la importación automática. '
             'Al guardar, recalcula el próximo disparo del cron de importación.'
    )
    categorias_importar = fields.Text(
        string='Lista de categorías a importar',
        help='Categorías separadas por comas y delimitadas por comillas, como aparecen en la '
             'columna "Menu Nvl 1" del CSV (se ignoran mayúsculas y espacios repetidos). '
             'Dejar vacío para importar todo. Si alguna deja de coincidir con el CSV, se '
             'muestra una alerta en este formulario y en la bitácora.'
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
        help='Último respaldo manual: se usa solo si el CSV no incluye tipo de cambio Y la moneda USD no está configurada en el sistema Odoo.'
    )
    dias_ausencia_maxima = fields.Integer(
        string='Días máximos de ausencia',
        default=15,
        required=True,
        help='Si un producto lleva más de este número de días sin aparecer en el CSV '
             'de Syscom, se despublica de la tienda web — tras confirmarlo contra la '
             'API de ficha de producto (ver README.md), para no despublicar por una '
             'falla externa prolongada del CSV. Si hay un filtro de categorías activo '
             '(categorias_importar), solo se evalúan productos de esas categorías — '
             'el propósito del filtro es incluir, no excluir.'
    )
    dias_retencion_bitacora_publicaciones = fields.Integer(
        string='Días de retención — bitácora de publicaciones',
        default=180,
        required=True,
        help='Los registros de syscom.publicacion.log (despublicaciones automáticas, '
             'ver dias_ausencia_maxima y existencia 0) más antiguos que este número de '
             'días se eliminan al final de cada importación. Un valor 0 o negativo '
             'desactiva la limpieza — se conservan indefinidamente.'
    )
    # MEJORA-75: monitoreo de categorías del CSV contra categorias_importar.
    categorias_csv_ultima = fields.Text(
        string='Categorías del último CSV',
        readonly=True,
        help='JSON {categoría: productos} con los valores de "Menu Nvl 1" del último CSV procesado.'
    )
    categorias_csv_conocidas = fields.Text(
        string='Categorías revisadas',
        readonly=True,
        help='JSON con las categorías del CSV ya revisadas. Se inicializa en la primera '
             'importación y se actualiza con el botón "Marcar categorías como revisadas".'
    )
    alerta_categorias = fields.Text(
        string='Alerta de categorías',
        compute='_compute_alerta_categorias',
        store=True,
        help='Filtros de categorias_importar que no coinciden con ninguna categoría del '
             'último CSV, y categorías nuevas del CSV aún no revisadas.'
    )
    version_modulo = fields.Char(
        string='Versión del módulo',
        compute='_compute_version_modulo',
        help='Versión instalada de este módulo (ir.module.module.latest_version). '
             'La misma versión se registra en el log de Odoo al inicio de cada '
             'ejecución — ver ejecutar_importacion en syscom_importador.py.'
    )

    @api.depends('categorias_importar', 'categorias_csv_ultima', 'categorias_csv_conocidas')
    def _compute_alerta_categorias(self):
        for record in self:
            record.alerta_categorias = record._texto_alerta_categorias() or False

    def _texto_alerta_categorias(self) -> str:
        """Compara el filtro y las categorías revisadas contra las del último CSV."""
        self.ensure_one()
        if not self.categorias_csv_ultima:
            return ''
        conteo = {
            nombre: n for nombre, n in json.loads(self.categorias_csv_ultima).items()
            if normalizar_categoria(nombre) not in _CATEGORIAS_PLACEHOLDER
        }
        nombre_por_clave = {normalizar_categoria(nombre): nombre for nombre in conteo}
        lineas = []

        sin_coincidencia = []
        for filtro in parsear_categorias(self.categorias_importar):
            if normalizar_categoria(filtro) in nombre_por_clave:
                continue
            parecida = difflib.get_close_matches(
                normalizar_categoria(filtro), list(nombre_por_clave), n=1, cutoff=0.5
            )
            sugerencia = f' (¿"{nombre_por_clave[parecida[0]]}"?)' if parecida else ''
            sin_coincidencia.append(f'"{filtro}"{sugerencia}')
        if sin_coincidencia:
            lineas.append('Filtros sin coincidencia en el CSV (no se importa nada de ellos): '
                          + ', '.join(sin_coincidencia))

        conocidas = {normalizar_categoria(c) for c in json.loads(self.categorias_csv_conocidas or '[]')}
        nuevas = [
            f'"{nombre}" ({n} productos)' for nombre, n in sorted(conteo.items(), key=lambda x: -x[1])
            if normalizar_categoria(nombre) not in conocidas
        ]
        if nuevas:
            lineas.append('Categorías nuevas en el CSV, sin revisar: ' + ', '.join(nuevas))
        return '\n'.join(lineas)

    def action_marcar_categorias_revisadas(self):
        """Da por revisadas las categorías del último CSV: dejan de reportarse como nuevas."""
        for record in self:
            record.categorias_csv_conocidas = json.dumps(
                sorted(json.loads(record.categorias_csv_ultima or '{}')), ensure_ascii=False
            )

    def _compute_version_modulo(self):
        for record in self:
            record.version_modulo = record._obtener_version_modulo()

    def _obtener_version_modulo(self) -> str:
        """Versión instalada de este módulo, consultada vía ir.module.module
        (no leída directamente del __manifest__.py: así refleja lo que Odoo
        realmente tiene registrado como instalado/actualizado)."""
        modulo = self.env['ir.module.module'].sudo().search(
            [('name', '=', _NOMBRE_MODULO)], limit=1
        )
        return modulo.latest_version or 'desconocida'

    @api.model
    def get_config(self):
        """Obtener la configuración activa"""
        config = self.search([], limit=1)
        if not config:
            raise UserError('No hay configuración de Syscom definida.')
        return config

    def write(self, vals):
        res = super().write(vals)
        if 'hora_ejecucion' in vals:
            self._actualizar_nextcall_cron(vals['hora_ejecucion'])
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for vals in vals_list:
            if 'hora_ejecucion' in vals:
                records._actualizar_nextcall_cron(vals['hora_ejecucion'])
        return records

    def _actualizar_nextcall_cron(self, hora_ejecucion):
        """Recalcula `nextcall` del cron de importación a la próxima ocurrencia
        de `hora_ejecucion` (hoy si todavía no pasó esa hora, mañana en caso
        contrario). `hora_ejecucion` se interpreta en UTC, igual que el resto
        del módulo (ver uso de datetime.utcnow() en _actualizar_syscom_provider_sql_batch).
        No altera interval_number/interval_type: solo re-ancla el próximo disparo;
        los siguientes los sigue calculando Odoo sumando el intervalo configurado.
        """
        cron = self.env.ref('product_import_syscom.ir_cron_syscom_import', raise_if_not_found=False)
        if not cron:
            return
        horas_enteras = int(hora_ejecucion)
        minutos = round((hora_ejecucion - horas_enteras) * 60)
        if minutos == 60:
            horas_enteras, minutos = horas_enteras + 1, 0
        horas_enteras %= 24

        ahora = datetime.utcnow()
        proxima_ejecucion = ahora.replace(hour=horas_enteras, minute=minutos, second=0, microsecond=0)
        if proxima_ejecucion <= ahora:
            proxima_ejecucion += timedelta(days=1)

        cron.write({'nextcall': proxima_ejecucion})
        if var._logger_info:
            _logger.info(
                'syscom.config: nextcall del cron de importación actualizado a %s UTC (hora_ejecucion=%.2f)',
                proxima_ejecucion, hora_ejecucion,
            )


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
import logging

var = Parametros()
_logger = logging.getLogger(__name__)
_logger.addFilter(FuncNameFilter())


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
        help='Último respaldo manual: se usa solo si el CSV no incluye tipo de cambio Y la moneda USD no está configurada en el sistema Odoo.'
    )
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

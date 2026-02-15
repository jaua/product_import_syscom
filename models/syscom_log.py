# ===========================
# models/syscom_log.py
# ===========================
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SyscomLog(models.Model):
    _name = 'syscom.log'
    _description = 'Bitácora de importaciones Syscom'
    _order = 'fecha_descarga desc'
    _rec_name = 'fecha_descarga'

    fecha_descarga = fields.Datetime(
        string='Fecha de descarga',
        required=True,
        default=fields.Datetime.now
    )
    tamano_descarga = fields.Char(
        string='Tamaño de descarga',
        required=True
    )
    ruta_archivo = fields.Char(
        string='Ruta del archivo',
        required=True
    )
    url_origen = fields.Char(
        string='URL de origen',
        required=True
    )
    categorias_importadas = fields.Text(
        string='Categorías importadas',
        required=True
    )
    tasa_cambio = fields.Float(
        string='Tasa de cambio',
        help='Tasa de cambio usada durante la importación (USD → moneda local)'
    )
    tipo_accion = fields.Char(
        string='Tipo de acción',
        required=True,
        default='Descarga CSV'
    )

    @api.model
    def create(self, vals):
        """Override create to log creation of SyscomLog entries."""
        record = super(SyscomLog, self).create(vals)
        _logger.info(f"SyscomLog llamada a created: {record.id} con fecha {record.fecha_descarga}")
        return record
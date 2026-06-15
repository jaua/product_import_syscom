from odoo import models, fields
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

    # BUG-33: override de create eliminado — solo instanciaba Parametros() en cada
    # registro para emitir un log. El log ya existe en _log_crear (syscom_config.py).
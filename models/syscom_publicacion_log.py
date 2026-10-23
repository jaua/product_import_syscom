from odoo import models, fields


class SyscomPublicacionLog(models.Model):
    _name = 'syscom.publicacion.log'
    _description = 'Bitácora de Publicaciones/Despublicaciones Syscom'
    _order = 'fecha desc'
    _rec_name = 'default_code'

    # product_tmpl_id con ondelete='set null' (no required): si el producto se
    # elimina más adelante, el registro histórico se conserva — default_code
    # es una foto del momento del evento, no un related, precisamente para
    # que sobreviva aunque el producto cambie o se borre después.
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Producto',
        ondelete='set null',
        index=True,
    )
    default_code = fields.Char(
        string='Referencia Interna',
        required=True,
        index=True,
    )
    evento = fields.Selection(
        [('despublicado', 'Despublicado')],
        string='Evento',
        default='despublicado',
        required=True,
        help="Por ahora el módulo solo despublica automáticamente — nunca publica "
             "por sí mismo (la publicación sigue siendo decisión manual). Este campo "
             "queda listo para un futuro 'publicado' si algún día se agrega esa lógica."
    )
    motivo = fields.Selection(
        [
            ('existencia_cero', 'Existencia reportada en 0'),
            ('ausencia_confirmada', 'Ausencia confirmada por API (posible descontinuación)'),
        ],
        string='Motivo',
        required=True,
    )
    detalle = fields.Char(
        string='Detalle',
        help='Contexto adicional del evento (p. ej. días de ausencia al momento de despublicar).'
    )
    fecha = fields.Datetime(
        string='Fecha',
        required=True,
        default=fields.Datetime.now,
    )

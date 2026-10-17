from odoo import models, fields, api

# Tabla de almacenamiento de la información en el csv que se importa
# no todos los campos, pero los que nos interesan.

class ProductProviderSyscom(models.Model):
    _name = "product.provider.syscom"
    _description = "Syscom Provider Product Info"
    _rec_name = "id_syscom"

    # ------------------------
    # Relaciones
    # ------------------------

    partner_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        required=True,
        domain=[('supplier_rank', '>', 0)],
        index=True,
    )

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Producto",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # opcional: para búsquedas rápidas
    default_code = fields.Char(
        string="Referencia Interna",
        related="product_tmpl_id.default_code",
        store=True,
        index=True,
    )

    # ------------------------
    # Datos Syscom
    # ------------------------

    id_syscom = fields.Char(
        string="ID Producto",
        required=True,
        index=True,
    )

    syscom_url = fields.Char(
        string="URL Producto",
    )

    syscom_url_imagen = fields.Char(
        string="URL Imagen",
    )

    # Cabezera: Existencias
    syscom_inventory = fields.Integer(
        string="Inventario Syscom",
        default=0,
    )

    # Cabezera: "Es Kit"
    es_kit = fields.Boolean(
        string="El Producto es un kit?",
        default=False,
    )

    syscom_obsoleto = fields.Boolean(
        string="Obsoleto",
        default=False,
    )

    # ------------------------
    # Campos adicionales útiles
    # ------------------------

    last_update = fields.Datetime(
        string="Última actualización",
    )

    ultima_vez_visto = fields.Datetime(
        string="Última vez visto en el CSV",
        default=fields.Datetime.now,
        help="Última vez que este código apareció en el CSV de Syscom. Se usa "
             "para detectar productos descontinuados: si lleva más de "
             "syscom.config.dias_ausencia_maxima sin aparecer, el template se "
             "despublica (tras confirmarlo contra la API de ficha de producto)."
    )

    active = fields.Boolean(
        default=True
    )

    # ------------------------
    # Restricciones
    # ------------------------

    _sql_constraints = [
        (
            "unique_syscom_product",
            "unique(id_syscom, partner_id)",
            "El ID de Syscom debe ser único por proveedor."
        ),
    ]

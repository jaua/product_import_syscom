from odoo import models, fields, api


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

    syscom_inventory = fields.Integer(
        string="Inventario Syscom",
        default=0,
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
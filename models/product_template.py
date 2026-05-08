from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_url_ref = fields.Text(
        string='URL referencia',
        help='Enlace del producto en el sitio web del proveedor.',
    )
    product_url_image = fields.Text(
        string='URL Imagen',
        help='Enlace a la imagen del producto en el sitio web del proveedor.',
    )
    syscom_ids = fields.One2many(
        "product.provider.syscom",
        "product_tmpl_id",
        string="Syscom Info"
    )

    def action_import_from_syscom(self):
        """Acción para importar desde Syscom"""
        config = self.env['syscom.config'].get_config()
        return config.ejecutar_importacion()

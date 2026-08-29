from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    syscom_ids = fields.One2many(
        "product.provider.syscom",
        "product_tmpl_id",
        string="Syscom Info"
    )

    # product_url_ref / product_url_image ya no se almacenan directamente en
    # product.template: se calculan desde product.provider.syscom (fuente
    # única de verdad) para eliminar la escritura duplicada del mismo dato
    # en dos modelos durante la importación.
    product_url_ref = fields.Text(
        string='URL referencia',
        compute='_compute_syscom_urls',
        help='Enlace del producto en el sitio web del proveedor (Syscom).',
    )
    product_url_image = fields.Text(
        string='URL Imagen',
        compute='_compute_syscom_urls',
        help='Enlace a la imagen del producto en el sitio web del proveedor (Syscom).',
    )

    @api.depends('syscom_ids.syscom_url', 'syscom_ids.syscom_url_imagen')
    def _compute_syscom_urls(self):
        for product in self:
            info = product.syscom_ids[:1]
            product.product_url_ref = info.syscom_url or False
            product.product_url_image = info.syscom_url_imagen or False

    def action_import_from_syscom(self):
        """Acción para importar desde Syscom"""
        config = self.env['syscom.config'].get_config()
        return config.ejecutar_importacion()

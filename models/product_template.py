# ===========================
# models/product_template.py
# ===========================
from odoo import models
from odoo import fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    syscom_url = fields.Text(string='URL', help='Enlace SYSCOM del producto importado.')
    syscom_url_image = fields.Text(string='URL Imagen', help='Enlace SYSCOM de la imagen del producto importado.')

    def action_import_from_syscom(self):
        """Acción para importar desde Syscom"""
        config = self.env['syscom.config'].get_config()
        return config.ejecutar_importacion()

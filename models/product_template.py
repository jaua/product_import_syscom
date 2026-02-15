# ===========================
# models/product_template.py
# ===========================
from odoo import models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def action_import_from_syscom(self):
        """Acción para importar desde Syscom"""
        config = self.env['syscom.config'].get_config()
        return config.ejecutar_importacion()
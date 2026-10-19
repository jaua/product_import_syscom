# ===========================
# __manifest__.py
# ===========================
{
    'name': 'Syscom Importador de productos',
    'version': '18.0.1.21.0',
    'category': 'Sales',
    'summary': 'Importación automática de productos desde Syscom',
    'description': """
        Módulo para la importación automática de productos desde el proveedor Syscom.
        - Descarga automática de archivos CSV, con hora de ejecución configurable
        - Configuración de categorías y márgenes de ganancia
        - Bitácora de importaciones
        - Actualización automática de productos (precios, inventario, categorías)
        - Despublicación web automática por existencia 0 o por ausencia prolongada
          del CSV (confirmada contra la API de ficha de producto de Syscom)
        - Sincronización de la descripción eCommerce desde esa misma API
        - Homologación de categorías a la jerarquía Todos/All
    """,
    'author': 'JAUA SyTI',
    'website': 'https://app.jauamx.com',
    'depends': ['base', 'product', 'purchase', 'sale', 'cdfi_invoice', 'website_sale'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/syscom_config_views.xml',
        'views/syscom_log_views.xml',
        'views/product_template_views.xml',
        'views/menu_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'auto_install': False,
}
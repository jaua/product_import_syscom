# ===========================
# __manifest__.py
# ===========================
{
    'name': 'Syscom Importador de productos',
    'version': '1.0',
    'category': 'Purchases',
    'summary': 'Importación automática de productos desde Syscom',
    'description': """
        Módulo para la importación automática de productos desde el proveedor Syscom.
        - Descarga automática de archivos CSV
        - Configuración de categorías y márgenes de ganancia
        - Bitácora de importaciones
        - Actualización automática de productos
    """,
    'author': 'JAUA SyTI',
    'website': 'https://app.jauamx.com',
    'depends': ['base', 'product', 'purchase'],
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
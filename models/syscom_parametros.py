class SyscomParametros():
    _proveedor_nombre = "Syscom"
    _ruta_descarga = "/tmp/syscom_downloads"
    _archivo_prueba = f"{_ruta_descarga}/verifica.txt"
    _archivo_csv_prefijo = "syscom_products_"
    _archivo_csv_extension = ".csv"
    _archivo_bitacora_precios = f"{_ruta_descarga}/syscom_precios_bitacora.txt"
    _usar_bitacora_precios = True
    _tiempo_espera_descarga = 300
    _periodo_actualizaciones = 5
    _id_objetoimp = "02"
    _id_cat_unidad_medida = 1
    _categoria_separador = ' \ '
    _registros_por_batch = 2000
    _mxn_valor = 1.0
    _digitos_redondeo = 2
    _sin_marca_nombre = "S/M"
    _logger_info = True
    _logger_debug = False
    _logger_funcname = True  # prefija [nombre_funcion] en cada mensaje de log
    # MEJORA-48: atributos reservados para implementación futura — actualmente no consultados en código
    _mostrar_progreso = True      # pendiente: mostrar barra de progreso en UI
    _progreso_intervalo = 10      # pendiente: intervalo de actualización del progreso
    _actualizar_precios = True    # pendiente: toggle para omitir actualización de precios
    _actualizar_inventario = True # pendiente: toggle para omitir actualización de inventario
    _actualizar_url = True        # pendiente: toggle para omitir actualización de URL
    _actualizar_url_imagen = True # pendiente: toggle para omitir actualización de imagen
    _actualizar_obsoleto = True   # pendiente: toggle para marcar productos sin stock como obsoletos
    _crear_productos_nuevos = True # pendiente: toggle para omitir creación de productos nuevos
    _archivo_prueba = f"{_ruta_descarga}/verifica.txt"  # pendiente: verificación de conectividad
    _categoria_separador = ' \ '  # pendiente: separador de jerarquía de categorías en UI

    def __init__(self):
        # Atributo de instancia: su valor varía por ejecución y no debe ser compartido entre instancias
        # pendiente (BUG-32): _eliminar_archivo_previo ya no se consulta tras la refactorización
        self._eliminar_archivo_previo = True

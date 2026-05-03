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
    _mostrar_progreso = True
    _progreso_intervalo = 10
    _actualizar_precios = True
    _actualizar_inventario = True
    _actualizar_url = True
    _actualizar_url_imagen = True
    _actualizar_obsoleto = True
    _crear_productos_nuevos = True

    def __init__(self):
        # Atributo de instancia: su valor varía por ejecución y no debe ser compartido entre instancias
        self._eliminar_archivo_previo = True

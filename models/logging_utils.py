
# ===========================
# models/logging_utils.py
# ===========================
"""Utilidades de logging compartidas por el módulo. Sin dependencias del
ORM de Odoo — extraído de syscom_config.py a su propio archivo para que
también pueda aplicarse desde csv_utilerias.py y bitacora_precios.py sin
provocar un import circular con syscom_config.py.
"""
import logging
from .syscom_parametros import SyscomParametros as Parametros

var = Parametros()


class FuncNameFilter(logging.Filter):
    """Antepone '[nombre_función]' a cada mensaje de log, si
    var._logger_funcname está activo (ver syscom_parametros.py)."""

    def filter(self, record):
        if var._logger_funcname:
            record.msg = f'[{record.funcName}] {record.msg}'
        return True

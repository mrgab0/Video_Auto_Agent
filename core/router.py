"""
Enrutador Determinista de Fuentes Visuales y Audio.
Maneja decisiones de fallback sin invocar LLMs, ahorrando tokens y garantizando confiabilidad.
"""

import os
from typing import Tuple

class MediaRouter:
    @staticmethod
    def select_visual_source() -> str:
        """
        Determina qué proveedor de video usar basándose en la configuración de entorno:
        - Si FAL_KEY está activa y no es placeholder: 'fal_ai'
        - Fallback automático: 'pexels'
        """
        fal_key = os.environ.get("FAL_KEY", "").strip()
        if fal_key and not fal_key.startswith("tu_clave"):
            return "fal_ai"
        return "pexels"

    @staticmethod
    def select_music_source() -> str:
        """
        Determina la fuente de música instrumental:
        - Si TREBLO_API_KEY está configurada: 'treblo'
        - Fallback automático: 'local_library' (assets/music/)
        """
        treblo_key = os.environ.get("TREBLO_API_KEY", "").strip()
        if treblo_key and not treblo_key.startswith("tu_clave"):
            return "treblo"
        return "local_library"

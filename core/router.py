"""
Enrutador Determinista de Fuentes Visuales y Audio.
Maneja decisiones de fallback sin invocar LLMs, ahorrando tokens y garantizando confiabilidad.
"""

import os

class MediaRouter:
    @staticmethod
    def select_visual_source() -> str:
        """
        Determina qué proveedor de video usar basándose en la configuración de entorno:
        1. 'gemini_omni' si GEMINI_API_KEY está activa (consume tokens de Google).
        2. 'fal_ai' si FAL_KEY está activa.
        3. 'pexels' como fallback universal de stock real.
        """
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_key and not gemini_key.startswith("tu_clave"):
            return "gemini_omni"

        fal_key = os.environ.get("FAL_KEY", "").strip()
        if fal_key and not fal_key.startswith("tu_clave"):
            return "fal_ai"

        return "pexels"

    @staticmethod
    def select_music_source() -> str:
        """
        Determina la fuente de música instrumental:
        - Si JAMENDO_CLIENT_ID está configurada: 'jamendo' (catálogo libre instrumental)
        - Si TREBLO_API_KEY está configurada: 'treblo'
        - Fallback automático: 'local_library' (assets/music/)
        """
        jamendo_id = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
        if jamendo_id and not jamendo_id.startswith("tu_clave"):
            return "jamendo"

        treblo_key = os.environ.get("TREBLO_API_KEY", "").strip()
        if treblo_key and not treblo_key.startswith("tu_clave"):
            return "treblo"
        return "local_library"


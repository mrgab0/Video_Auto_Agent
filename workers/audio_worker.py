"""
Audio Worker: Generación concurrente de locución TTS vía ElevenLabs con soporte de caché SHA-256.
"""

import os
from pathlib import Path
from typing import Dict, Any
import video_mcp_server as server
import workers.mock_utils as mock_utils

class AudioWorker:
    @staticmethod
    def process(script_text: str, output_path: str, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """Ejecuta la síntesis de voz y medición de duración de forma aislada."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        has_key = bool(os.environ.get("ELEVENLABS_API_KEY") and not os.environ.get("ELEVENLABS_API_KEY").startswith("tu_clave"))
        
        if dry_run or not has_key:
            mock_utils.create_mock_voiceover(output_path, duration_sec=45)
            dur_us = server.get_media_duration_us(output_path)
            return {
                "success": True,
                "voice_path": output_path,
                "duration_s": dur_us / 1_000_000,
                "mode": "mock"
            }

        try:
            res = server.generate_voiceover_elevenlabs(
                text=script_text,
                output_path=output_path,
                voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "TX3LPaxmHKxFdv7VOQHJ"),
                model_id="eleven_multilingual_v2",
                trim_silence=True,
                force_refresh=force
            )
        except Exception as e:
            res = str(e)

        # Si ElevenLabs falló por cuota (quota_exceeded) o error, activar TTS neural de respaldo
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 10000:
            print("  ⚠️ Cuota de ElevenLabs agotada. Activando voz neural de respaldo en español...")
            from workers.tts_fallback import generate_neural_tts
            fallback_ok = generate_neural_tts(script_text, output_path, voice="es-MX-JorgeNeural")
            if not fallback_ok or not os.path.exists(output_path) or os.path.getsize(output_path) < 10000:
                raise RuntimeError(f"Error generando locución con ElevenLabs y Fallback: {res}")
            print(f"  🎙️ Locución neural de alta calidad generada con éxito en: {output_path}")

        dur_us = server.get_media_duration_us(output_path)
        return {
            "success": True,
            "voice_path": output_path,
            "duration_s": dur_us / 1_000_000,
            "message": res
        }

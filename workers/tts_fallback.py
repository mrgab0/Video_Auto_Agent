"""
TTS Fallback Engine:
Si ElevenLabs se queda sin cuota de caracteres, conmuta automáticamente a Edge TTS (Microsoft Azure Neural)
100% gratuito, sin límites de tokens y con voces hiperrealistas en español neutro (es-MX-JorgeNeural / es-ES-AlvaroNeural).
"""

import os
import subprocess
from pathlib import Path

def generate_neural_tts(text: str, output_path: str, voice: str = "es-MX-JorgeNeural") -> bool:
    """Genera locución neural en español usando Edge TTS (sin cuota y sin costo)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    raw_path = output_path + ".raw_tts.mp3"

    try:
        # Intentar con edge-tts si está instalado o pip
        cmd_test = subprocess.run(["which", "edge-tts"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if cmd_test.returncode != 0:
            print("  📦 Instalando edge-tts ligero...")
            subprocess.run(["pip", "install", "-q", "edge-tts"], check=True)

        cmd = [
            "edge-tts",
            "--voice", voice,
            "--text", text,
            "--write-media", raw_path
        ]
        subprocess.run(cmd, check=True)

        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 5000:
            # Recortar silencios con FFmpeg para mantener ritmo viral
            trim_cmd = [
                "ffmpeg", "-y", "-i", raw_path,
                "-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB:stop_periods=-1:stop_duration=0.3:stop_threshold=-50dB",
                "-c:a", "libmp3lame", "-b:a", "192k",
                output_path
            ]
            subprocess.run(trim_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(raw_path):
                os.remove(raw_path)
            return True

        return False
    except Exception as e:
        print(f"  ⚠️ Error en Edge TTS: {e}")
        return False

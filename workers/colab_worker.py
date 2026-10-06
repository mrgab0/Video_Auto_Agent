"""
Colab Worker: Cliente ligero para consumir Google Colab propio (Gradio / ComfyUI / Cloudflare Tunnel)
como backend de GPU 100% gratuito para generación de video IA (SVD / Wan 2.1).
"""

import os
import time
import requests
import subprocess
from pathlib import Path
from typing import Optional

class ColabWorker:
    @staticmethod
    def is_configured() -> bool:
        """Verifica si hay una URL de Colab activa en variables de entorno."""
        url = os.environ.get("COLAB_API_URL", "").strip()
        return bool(url and not url.startswith("tu_url"))

    @classmethod
    def generate_video_clip(
        cls,
        prompt: str,
        output_path: str,
        duration_sec: int = 8,
        image_url: Optional[str] = None
    ) -> bool:
        """
        Envía la tarea al Google Colab conectado vía Gradio o REST API y descarga el MP4 generado.
        """
        base_url = os.environ.get("COLAB_API_URL", "").strip().rstrip("/")
        if not base_url or base_url.startswith("tu_url"):
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        raw_output = output_path + ".colab_raw.mp4"

        try:
            # 1. Detección automática: Gradio API (/api/predict)
            predict_url = f"{base_url}/api/predict"
            payload = {
                "data": [
                    prompt,
                    image_url or "",
                    duration_sec,
                    127,  # motion bucket id
                    6     # fps
                ]
            }

            headers = {"Content-Type": "application/json"}
            print(f"  ☁️ Conectando con Google Colab GPU en {base_url}...")
            res = requests.post(predict_url, json=payload, headers=headers, timeout=240)

            video_download_url = None
            if res.status_code == 200:
                data = res.json()
                # Extraer url del resultado de Gradio
                if isinstance(data.get("data"), list) and len(data["data"]) > 0:
                    item = data["data"][0]
                    if isinstance(item, dict) and "name" in item:
                        video_download_url = f"{base_url}/file={item['name']}"
                    elif isinstance(item, str) and (item.startswith("http") or item.endswith(".mp4")):
                        video_download_url = item if item.startswith("http") else f"{base_url}/file={item}"

            # 2. Fallback a endpoint REST genérico de ComfyUI
            if not video_download_url:
                comfy_url = f"{base_url}/prompt"
                # Si es ComfyUI directo
                res_comfy = requests.get(f"{base_url}/history", timeout=10)
                if res_comfy.status_code == 200:
                    print("  ℹ️ Detectado backend ComfyUI en Colab...")
                    # Manejar respuesta ComfyUI
                    pass

            # 3. Descargar el archivo MP4 resultante si se obtuvo URL
            if video_download_url:
                print(f"  📥 Descargando video generado desde Colab...")
                curl_cmd = [
                    "curl", "-s", "-L",
                    "--max-time", "120",
                    "-o", raw_output,
                    video_download_url
                ]
                subprocess.run(curl_cmd, check=True)

                if os.path.exists(raw_output) and os.path.getsize(raw_output) > 20000:
                    # Normalizar a 30fps CFR 1080x1920 con FFmpeg
                    cmd = [
                        "ffmpeg", "-y",
                        "-stream_loop", "-1", "-i", raw_output,
                        "-t", str(duration_sec),
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                        "-r", "30",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
                        output_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    if os.path.exists(raw_output):
                        os.remove(raw_output)

                    if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                        return True

            return False
        except Exception as e:
            print(f"  ⚠️ Colab no disponible o falló conexión: {e}")
            if os.path.exists(raw_output):
                os.remove(raw_output)
            return False

"""
Music Worker: Preparación y selección de música ambiental con fallback determinista.
"""

import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
import video_mcp_server as server
import workers.mock_utils as mock_utils
from core.router import MediaRouter

class MusicWorker:
    @staticmethod
    def process(output_path: str, duration_sec: int, project_name: str, dry_run: bool = False) -> str:
        """Obtiene o corta la pista de fondo para el video."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and output_file.stat().st_size > 5000:
            return str(output_file)

        mode = MediaRouter.select_music_source()

        if mode == "treblo" and not dry_run:
            try:
                res = server.generate_background_music_treblo(
                    prompt=f"ambient cinematic instrumental background music for {project_name}",
                    output_path=str(output_file),
                    duration_sec=duration_sec + 5
                )
                if output_file.exists() and output_file.stat().st_size > 5000:
                    return str(output_file)
            except Exception:
                pass

        # Fallback a biblioteca local en assets/music/
        assets_dir = Path(__file__).parent.parent / "assets" / "music"
        available_tracks = list(assets_dir.glob("*.mp3")) if assets_dir.exists() else []

        if available_tracks:
            selected_track = random.choice(available_tracks)
            fade_out_start = max(0, duration_sec - 2)
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", str(selected_track),
                "-t", str(duration_sec + 3),
                "-af", f"afade=t=in:ss=0:d=1,afade=t=out:st={fade_out_start}:d=2",
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(output_file)
            ]
            subprocess.run(trim_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return str(output_file)

        # Fallback sintético mínimo si no hubiera archivos de música
        mock_utils.create_ambient_music_placeholder(str(output_file), duration_sec=duration_sec)
        return str(output_file)

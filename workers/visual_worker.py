"""
Visual Worker: Generación y descarga paralela de clips 9:16 por escena.
Soporta ThreadPoolExecutor para fan-out masivo y enrutamiento inteligente.
"""

import os
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import video_mcp_server as server
import workers.mock_utils as mock_utils
from core.router import MediaRouter

class VisualWorker:
    @staticmethod
    def _process_single_clip(prompt: str, clip_path: str, scene_idx: int, dry_run: bool = False) -> str:
        """Genera o descarga un clip individual de 8 segundos."""
        clip_dur = 8
        if dry_run:
            mock_utils.create_mock_video_clip(clip_path, duration_sec=clip_dur, color="darkblue", label=f"Escena {scene_idx}")
            return clip_path

        retries = 0
        while (not os.path.exists(clip_path) or os.path.getsize(clip_path) < 20000) and retries < 3:
            retries += 1
            server.generate_cinematic_scene_clip(
                prompt=prompt,
                output_path=clip_path,
                duration_sec=clip_dur,
                scene_index=scene_idx
            )

        if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 20000:
            raise RuntimeError(f"Error generando clip para escena {scene_idx}: {clip_path}")

        return clip_path

    @classmethod
    def process_all_scenes(cls, scenes: List[str], project_dir: Path, dry_run: bool = False, max_workers: int = 3) -> List[str]:
        """
        Ejecuta el fan-out de generación de clips en paralelo usando ThreadPoolExecutor.
        """
        project_dir = Path(project_dir)
        tasks = []
        clip_paths = [str(project_dir / f"clip_{idx+1:02d}.mp4") for idx in range(len(scenes))]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(cls._process_single_clip, prompt, clip_paths[idx], idx+1, dry_run): idx
                for idx, prompt in enumerate(scenes)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    future.result()
                except Exception as e:
                    raise RuntimeError(f"Fallo en worker visual para escena {idx+1}: {e}")

        return clip_paths

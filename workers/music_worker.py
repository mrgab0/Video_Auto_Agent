"""
Music Worker: Preparación y selección de música ambiental con fallback determinista.
"""

import json
import os
import random
import shutil
import subprocess
import requests
from pathlib import Path
from typing import Dict, Any
import video_mcp_server as server
import workers.mock_utils as mock_utils
from core.router import MediaRouter


class MusicWorker:
    @staticmethod
    def _fetch_from_jamendo(output_file: Path, duration_sec: int, project_name: str) -> bool:
        """Descarga una pista instrumental cinemática desde Jamendo API evitando pistas repetidas."""
        client_id = os.environ.get("JAMENDO_CLIENT_ID")
        if not client_id or client_id.startswith("tu_clave"):
            return False

        history_file = Path(__file__).parent.parent / ".history_music.json"
        used_track_ids = set()
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    used_track_ids = set(json.load(f))
            except Exception:
                used_track_ids = set()

        search_terms = ["ambient", "suspense", "mystery", "soundtrack", "cinematic", "drone", "dark"]
        random.shuffle(search_terms)

        for term in search_terms:
            try:
                url = (
                    f"https://api.jamendo.com/v3.0/tracks/?client_id={client_id}"
                    f"&format=json&limit=25&tags=soundtrack&search={term}"
                    f"&include=musicinfo&boost=popularity_total"
                )
                res = requests.get(url, timeout=12)
                if res.status_code != 200:
                    continue

                results = res.json().get("results", [])
                # Filtrar estrictamente pistas instrumentales sin voces y con enlace de descarga
                instrumental_tracks = [
                    t for t in results
                    if t.get("musicinfo", {}).get("vocalinstrumental") == "instrumental"
                    and (t.get("audiodownload") or t.get("audio"))
                    and t.get("duration", 0) >= duration_sec
                ]

                # Filtrar pistas no usadas previamente
                fresh_tracks = [t for t in instrumental_tracks if str(t.get("id")) not in used_track_ids]
                candidate_pool = fresh_tracks if fresh_tracks else instrumental_tracks

                if candidate_pool:
                    chosen = random.choice(candidate_pool)
                    track_id = str(chosen.get("id"))
                    download_url = chosen.get("audiodownload") or chosen.get("audio")

                    raw_music = str(output_file) + ".raw.mp3"
                    dl_cmd = [
                        "curl", "-s", "-L",
                        "-A", "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0",
                        "--max-time", "35",
                        "-o", raw_music,
                        download_url
                    ]
                    subprocess.run(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

                    if os.path.exists(raw_music) and os.path.getsize(raw_music) > 10000:
                        fade_out_start = max(0, duration_sec - 2)
                        trim_cmd = [
                            "ffmpeg", "-y",
                            "-i", raw_music,
                            "-t", str(duration_sec + 3),
                            "-af", f"afade=t=in:ss=0:d=1,afade=t=out:st={fade_out_start}:d=2",
                            "-c:a", "libmp3lame", "-b:a", "192k",
                            str(output_file)
                        ]
                        subprocess.run(trim_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                        if os.path.exists(raw_music):
                            os.remove(raw_music)

                        if output_file.exists() and output_file.stat().st_size > 10000:
                            used_track_ids.add(track_id)
                            try:
                                with open(history_file, "w", encoding="utf-8") as f:
                                    json.dump(list(used_track_ids)[-100:], f)
                            except Exception:
                                pass
                            return True
            except Exception:
                continue

        return False

    @staticmethod
    def process(output_path: str, duration_sec: int, project_name: str, dry_run: bool = False) -> str:
        """Obtiene o corta la pista de fondo para el video garantizando variedad e instrumental puro."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and output_file.stat().st_size > 5000:
            return str(output_file)

        mode = MediaRouter.select_music_source()

        if mode == "jamendo" and not dry_run:
            if MusicWorker._fetch_from_jamendo(output_file, duration_sec, project_name):
                return str(output_file)

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

        # Fallback a biblioteca local en assets/music/ con rotación por historial
        assets_dir = Path(__file__).parent.parent / "assets" / "music"
        available_tracks = list(assets_dir.glob("*.mp3")) if assets_dir.exists() else []

        if available_tracks:
            history_file = Path(__file__).parent.parent / ".history_music.json"
            used_tracks = set()
            if history_file.exists():
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        used_tracks = set(json.load(f))
                except Exception:
                    used_tracks = set()

            fresh_local = [t for t in available_tracks if t.name not in used_tracks]
            selected_track = random.choice(fresh_local) if fresh_local else random.choice(available_tracks)

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

            used_tracks.add(selected_track.name)
            try:
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(list(used_tracks)[-100:], f)
            except Exception:
                pass

            return str(output_file)

        # Fallback sintético mínimo si no hubiera archivos de música
        mock_utils.create_ambient_music_placeholder(str(output_file), duration_sec=duration_sec)
        return str(output_file)


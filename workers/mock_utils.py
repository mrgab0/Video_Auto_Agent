"""
Utilidades para generación de assets simulados en modo dry-run.
"""

import os
import subprocess
from pathlib import Path

def create_mock_voiceover(output_path: str, duration_sec: int = 45):
    """Crea una pista de voz silenciosa/placeholder para pruebas sin gastar ElevenLabs."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono",
        "-t", str(duration_sec),
        "-c:a", "libmp3lame", "-b:a", "128k",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def create_mock_video_clip(output_path: str, duration_sec: int = 8, color: str = "darkblue", label: str = ""):
    """Crea un clip de video vertical 9:16 simulado para pruebas en modo dry-run."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    draw_filter = f",drawtext=text='{label}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2" if label else ""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=1080x1920:d={duration_sec}",
        "-vf", f"format=yuv420p{draw_filter}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def create_ambient_music_placeholder(output_path: str, duration_sec: int = 15):
    """Crea una pista de música ambiental sintética de fondo usando FFmpeg si no se provee una."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anoisesrc=d={duration_sec}:c=pink:r=44100:a=0.1",
        "-af", f"lowpass=f=400,afade=t=in:ss=0:d=1,afade=t=out:st={max(0, duration_sec - 1)}:d=1",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

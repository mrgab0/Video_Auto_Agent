"""
FFmpeg Render Engine: Ensamblado directo de video vertical 1080x1920 @ 30fps CFR.
"""

from typing import List
import video_mcp_server as server

class FFmpegEngine:
    @staticmethod
    def render(video_paths: List[str], voiceover_path: str, music_path: str, output_path: str) -> str:
        """Invoca el renderizador instantáneo calibrado para 30fps y niveles de volumen ideales."""
        return server.render_instant_video_ffmpeg(
            video_paths=video_paths,
            voiceover_path=voiceover_path,
            music_path=music_path,
            output_path=output_path
        )

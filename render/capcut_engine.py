"""
CapCut Engine: Generador de proyectos y borradores nativos de CapCut.
"""

from typing import List
import video_mcp_server as server

class CapCutEngine:
    @staticmethod
    def create_draft(project_name: str, video_paths: List[str], voiceover_path: str, music_path: str) -> str:
        """Genera el borrador nativo editable con pistas ordenadas y volúmenes 1.0 (voz) y 0.15 (música)."""
        return server.create_capcut_draft_project(
            project_name=project_name,
            video_paths=video_paths,
            voiceover_path=voiceover_path,
            music_path=music_path
        )

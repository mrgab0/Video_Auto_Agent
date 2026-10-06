"""
Módulo de Gestión de Estado Durable y Checkpointing para Video_Auto_Agent.
Garantiza tolerancia a fallos, caídas de conexión y reinicios en entornos móviles.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

class ExecutionState:
    def __init__(self, project_dir: Path, project_name: str):
        self.project_dir = Path(project_dir)
        self.project_name = project_name
        self.state_file = self.project_dir / "pipeline_state.json"
        self.data: Dict[str, Any] = {
            "project_name": project_name,
            "created_at": time.time(),
            "updated_at": time.time(),
            "status": "pending",
            "completed_nodes": [],
            "topic": None,
            "script_data": None,
            "voiceover_path": None,
            "voice_duration_s": 0.0,
            "clips": {},
            "music_path": None,
            "rendered_video_path": None,
            "capcut_draft_path": None,
            "social_kit": None,
            "errors": []
        }
        self.load()

    def load(self) -> None:
        """Carga el estado previo desde disco si existe."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception as e:
                print(f"⚠️ No se pudo leer el archivo de estado previo: {e}")

    def save(self) -> None:
        """Persiste el estado actual atómicamente en disco."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = time.time()
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.state_file)
        except Exception as e:
            print(f"⚠️ Error al guardar estado: {e}")

    def mark_completed(self, node_name: str, **kwargs) -> None:
        """Marca un nodo del grafo como completado y actualiza atributos."""
        if node_name not in self.data["completed_nodes"]:
            self.data["completed_nodes"].append(node_name)
        for k, v in kwargs.items():
            self.data[k] = v
        self.save()

    def is_completed(self, node_name: str) -> bool:
        """Verifica si un nodo ya ha sido completado previamente."""
        return node_name in self.data["completed_nodes"]

    def log_error(self, node_name: str, error_msg: str) -> None:
        """Registra un error en la traza del estado."""
        self.data["errors"].append({
            "node": node_name,
            "time": time.time(),
            "error": error_msg
        })
        self.save()

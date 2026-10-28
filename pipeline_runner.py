#!/usr/bin/env python3
"""
Orquestador Principal de Video_Auto_Agent.
Implementa el Arnés Agéntico con Graph Engineering, Fan-out Concurrente y Checkpointing.
Compatible con CLI independiente y Antigravity CLI ('agy').
"""

import os
import sys
import argparse
from pathlib import Path

# Cargar .env si existe
def load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and not os.environ.get(k):
                        os.environ[k] = v

load_dotenv()

from core.graph import GraphRunner

def main():
    parser = argparse.ArgumentParser(description="Video_Auto_Agent - Pipeline Agéntico de Video Vertical 9:16")
    parser.add_argument("--topic", type=str, default=None, help="Tema o idea para el video")
    parser.add_argument("--auto", action="store_true", help="Autogenerar tema viral con IA si no se especifica --topic")
    parser.add_argument("--project", type=str, default=None, help="Nombre del proyecto / carpeta de salida")
    parser.add_argument("--export-gallery", action="store_true", help="Copiar video final verificado a la Galería (/sdcard/Movies)")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulación sin consumo de APIs ni tokens")
    parser.add_argument("--force", action="store_true", help="Forzar regeneración ignorando checkpoints o cachés previos")
    parser.add_argument("--no-resume", action="store_true", help="Desactivar la reanudación automática desde checkpoints")

    args = parser.parse_args()

    if not args.topic and not args.auto:
        print("ℹ️ Video_Auto_Agent — Modo Seguro:")
        print("  Para crear un video especifica un tema o usa --auto:")
        print("    python3 pipeline_runner.py --topic \"El Incidente OVNI de Roswell\"")
        print("    python3 pipeline_runner.py --auto")
        print("  Para exportar el resultado a la Galería de Android añade: --export-gallery")
        sys.exit(0)

    runner = GraphRunner(
        project_name=args.project,
        topic=args.topic,
        dry_run=args.dry_run,
        force=args.force,
        resume=not args.no_resume,
        export_to_gallery=args.export_gallery
    )

    runner.run()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script de validación y prueba para el pipeline de automatización de video.
Verifica:
1. Generación y sintaxis de proyectos CapCut (draft_content.json y draft_meta_info.json).
2. Disponibilidad de FFmpeg y ffprobe en el sistema.
3. Variables de entorno (ELEVENLABS_API_KEY, GEMINI_API_KEY).
"""

import os
import sys
import json
import shutil
from pathlib import Path

# Importar funciones del servidor
import video_mcp_server as server

def test_system_dependencies():
    print("=== 1. Verificando Dependencias del Sistema ===")
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    python_version = sys.version.split()[0]
    
    print(f"Python: {python_version}")
    print(f"FFmpeg: {'OK -> ' + ffmpeg_path if ffmpeg_path else 'No encontrado'}")
    print(f"FFprobe: {'OK -> ' + ffprobe_path if ffprobe_path else 'No encontrado'}")

def test_api_keys():
    print("\n=== 2. Verificando Variables de Entorno ===")
    eleven_key = os.environ.get("ELEVENLABS_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    print(f"ELEVENLABS_API_KEY: {'Configurada' if eleven_key else 'NO configurada (opcional para pruebas de borrador)'}")
    print(f"GEMINI_API_KEY:     {'Configurada' if gemini_key else 'NO configurada (opcional para pruebas de borrador)'}")

def test_capcut_draft_creation():
    print("\n=== 3. Probando Generación de Borrador de CapCut ===")
    test_project = "test_poc_project"
    test_dir = os.path.abspath("./capcut_drafts")
    
    # Rutas simuladas
    video_paths = ["/fake/path/clip1.mp4", "/fake/path/clip2.mp4"]
    voiceover_path = "/fake/path/voice.mp3"
    music_path = "/fake/path/bg_music.mp3"
    
    res = server.create_capcut_draft_project(
        project_name=test_project,
        video_paths=video_paths,
        voiceover_path=voiceover_path,
        music_path=music_path,
        custom_draft_dir=test_dir
    )
    print(f"Resultado: {res}")
    
    draft_folder = os.path.join(test_dir, test_project)
    content_file = os.path.join(draft_folder, "draft_content.json")
    meta_file = os.path.join(draft_folder, "draft_meta_info.json")
    
    assert os.path.exists(content_file), "draft_content.json no fue creado"
    assert os.path.exists(meta_file), "draft_meta_info.json no fue creado"
    
    with open(content_file, "r", encoding="utf-8") as f:
        content = json.load(f)
    
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    print("\nValidación de datos del borrador:")
    print(f"- Canvas Ratio: {content['canvas_config']['ratio']} ({content['canvas_config']['width']}x{content['canvas_config']['height']})")
    print(f"- Tracks totales: {len(content['tracks'])}")
    print(f"- Pista de Video: {len(content['tracks'][0]['segments'])} segmentos")
    print(f"- Volumen Pista Voz: {content['tracks'][1]['segments'][0]['volume'] * 100}%")
    print(f"- Volumen Pista Música: {content['tracks'][2]['segments'][0]['volume'] * 100}%")
    print(f"- Draft Name: {meta['draft_name']}")
    print("\n[OK] ¡Generación de borrador validada con éxito!")

if __name__ == "__main__":
    test_system_dependencies()
    test_api_keys()
    test_capcut_draft_creation()

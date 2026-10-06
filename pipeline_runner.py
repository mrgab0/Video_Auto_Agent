#!/usr/bin/env python3
"""
Orquestador Integral de Automatización de Video:
Genera voz con ElevenLabs, clips con Google Veo 2.0 y ensambla el borrador de CapCut (o render FFmpeg).
Soporta generación multi-escena y sincronización automática de duración.
"""

import os
import sys
import json
import random
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List

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

import video_mcp_server as server


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


def create_mock_video_clip(output_path: str, duration_sec: int = 5, color: str = "darkblue", label: str = ""):
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


def run_pipeline(
    project_name: str,
    script_text: str,
    video_prompts: List[str],
    bg_music_path: str = None,
    social_kit: dict = None,
    render_ffmpeg: bool = True,
    cleanup: bool = False,
    force: bool = False,
    dry_run: bool = False
):
    print(f"\n=======================================================")
    print(f"🎬 INICIANDO PIPELINE DE VIDEO: {project_name}")
    print(f"=======================================================")
    
    project_dir = Path(f"./output/{project_name}").resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    
    voice_path = str(project_dir / "voiceover.mp3")
    music_path = bg_music_path or str(project_dir / "bg_ambient.mp3")
    
    # Guardar Social Kit para publicación
    if not social_kit:
        social_kit = server.generate_social_kit_with_gemini(script_text, topic=project_name)
    
    social_kit_file = project_dir / "social_kit.json"
    with open(social_kit_file, "w", encoding="utf-8") as f:
        json.dump(social_kit, f, indent=2, ensure_ascii=False)
    
    # ---------------------------------------------------------
    # 1. Generación de Locución (ElevenLabs con voz Liam y Caché)
    # ---------------------------------------------------------
    print("\n[1/4] 🎙️ Generando locución con ElevenLabs (Voz: Liam)...")
    has_eleven_key = bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_API_KEY") != "tu_clave_de_elevenlabs_aqui")
    
    if dry_run or not has_eleven_key:
        if not dry_run:
            print("  ⚠️ ELEVENLABS_API_KEY no detectada. Usando audio sintético simulado.")
        simulated_dur = max(4, int(len(script_text.split()) / 2.5))
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={simulated_dur}",
            "-c:a", "libmp3lame", voice_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"  ✅ Audio simulado generado en: {voice_path}")
    else:
        res = server.generate_voiceover_elevenlabs(
            text=script_text,
            output_path=voice_path,
            voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "TX3LPaxmHKxFdv7VOQHJ"),
            force_refresh=force
        )
        if not os.path.exists(voice_path):
            print(f"  ❌ {res}")
            sys.exit(1)
        print(f"  {res}")

    voice_duration_us = server.get_media_duration_us(voice_path)
    voice_duration_s = voice_duration_us / 1_000_000
    print(f"  ⏱️ Duración total de la locución: {voice_duration_s:.2f} segundos")

    # ---------------------------------------------------------
    # 2. Generación de Videos (Google Veo 2.0 / Multi-Escena)
    # ---------------------------------------------------------
    print(f"\n[2/4] 🎥 Generando clips de video 9:16...")
    has_gemini_key = bool(os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") != "tu_clave_de_google_ai_studio_aqui")
    
    video_paths = []
    for idx, prompt in enumerate(video_prompts):
        clip_path = str(project_dir / f"clip_{idx+1:02d}.mp4")
        print(f"\n  ▶ Escena {idx+1}/{len(video_prompts)}: \"{prompt}\"")
        clip_dur = 8  # Estándar estricto: 8.0 segundos continuos por escena
        
        if dry_run:
            create_mock_video_clip(clip_path, duration_sec=clip_dur, color="darkblue", label=f"Escena {idx+1}")
            print(f"  ✅ Clip {idx+1} generado en: {clip_path}")
        else:
            print(f"  🎨 Descargando video real 9:16 de Pexels (8s continuos)...")
            c_res = server.generate_cinematic_scene_clip(
                prompt=prompt,
                output_path=clip_path,
                duration_sec=clip_dur,
                scene_index=idx+1
            )
            print(f"  ✅ {c_res}")
            
        video_paths.append(clip_path)

    # ---------------------------------------------------------
    # COMPUERTA DE VERIFICACIÓN ESTRICTA DE ASSETS
    # ---------------------------------------------------------
    print("\n🔍 VERIFICANDO INTEGRIDAD DE TODOS LOS ASSETS ANTES DE LA UNIÓN...")
    
    if not os.path.exists(voice_path) or os.path.getsize(voice_path) < 10000:
        raise RuntimeError(f"El archivo de voz no existe o está corrupto: {voice_path}")
    print(f"  ✅ Locución verificada: {voice_duration_s:.2f}s ({os.path.getsize(voice_path):,} bytes)")

    verified_video_paths = []
    for idx, prompt in enumerate(video_prompts):
        clip_path = str(project_dir / f"clip_{idx+1:02d}.mp4")
        retries = 0
        while (not os.path.exists(clip_path) or os.path.getsize(clip_path) < 20000) and retries < 3:
            retries += 1
            print(f"  ⚠️ Reintentando descarga para Escena {idx+1} (intento {retries}/3)...")
            server.generate_cinematic_scene_clip(prompt, clip_path, duration_sec=8, scene_index=idx+1)
        
        if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 20000:
            raise RuntimeError(f"Error crítico: No se pudo generar el clip para la escena {idx+1} ({clip_path})")
        
        dur_us = server.get_media_duration_us(clip_path)
        print(f"  ✅ Clip {idx+1}/{len(video_prompts)} verificado en disco: {dur_us/1_000_000:.2f}s ({os.path.getsize(clip_path):,} bytes)")
        verified_video_paths.append(clip_path)

    video_paths = verified_video_paths
    total_video_dur = sum(server.get_media_duration_us(p) for p in video_paths) / 1_000_000
    print(f"\n  ⏱️ Duración total de metraje visual verificado: {total_video_dur:.2f}s (Audio: {voice_duration_s:.2f}s)")

    # ---------------------------------------------------------
    # 3. Música Instrumental de Fondo (15% de volumen)
    # ---------------------------------------------------------
    print("\n[3/4] 🎵 Preparando música instrumental de fondo (15% de volumen)...")
    if not os.path.exists(music_path):
        has_treblo = bool(os.environ.get("TREBLO_API_KEY") and not os.environ.get("TREBLO_API_KEY").startswith("tu_clave"))
        if has_treblo and not dry_run:
            print("  Solicitando música instrumental a Treblo.com API...")
            treblo_res = server.generate_background_music_treblo(
                prompt=f"ambient cinematic instrumental background music for {project_name}",
                output_path=music_path,
                duration_sec=int(voice_duration_s) + 5
            )
            print(f"  {treblo_res}")
        
        # Si Treblo no generó archivo (o 402 sin créditos), seleccionar pista real de estudio de assets/music/
        if not os.path.exists(music_path) or os.path.getsize(music_path) < 1000:
            music_assets_dir = Path(__file__).parent / "assets" / "music"
            available_tracks = list(music_assets_dir.glob("*.mp3")) if music_assets_dir.exists() else []
            if available_tracks:
                chosen_track = available_tracks[random.randint(0, len(available_tracks) - 1)]
                print(f"  🎵 Usando pista cinemática de estudio ({chosen_track.name})...")
                dur_target = int(voice_duration_s) + 5
                cmd = [
                    "ffmpeg", "-y", "-i", str(chosen_track),
                    "-t", str(dur_target),
                    "-af", f"afade=t=out:st={dur_target-3}:d=3",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    music_path
                ]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            else:
                print("  Creando pista instrumental de fondo sintética...")
                create_ambient_music_placeholder(music_path, duration_sec=int(voice_duration_s) + 4)
    print(f"  ✅ Música lista en: {music_path}")

    # ---------------------------------------------------------
    # 4. Creación de Borrador de CapCut
    # ---------------------------------------------------------
    print("\n[4/4] ✂️ Ensamblando borrador editable para CapCut...")
    draft_res = server.create_capcut_draft_project(
        project_name=project_name,
        video_paths=video_paths,
        voiceover_path=voice_path,
        music_path=music_path
    )
    print(f"  ✅ {draft_res}")

    # ---------------------------------------------------------
    # 5. Renderizado Directo Opcional con FFmpeg
    # ---------------------------------------------------------
    final_mp4 = None
    if render_ffmpeg:
        final_mp4 = str(project_dir / f"{project_name}_final.mp4")
        print(f"\n🎞️ Renderizando video final directo con FFmpeg en {final_mp4}...")
        render_res = server.render_instant_video_ffmpeg(
            video_paths=video_paths,
            voiceover_path=voice_path,
            music_path=music_path,
            output_path=final_mp4
        )
        print(f"  ✅ {render_res}")

        # Copiar automáticamente a la carpeta Movies de Android para visualización inmediata en Galería
        android_movies = "/sdcard/Movies"
        if os.path.exists(android_movies):
            import shutil
            try:
                gallery_dest = os.path.join(android_movies, f"{project_name}_final.mp4")
                shutil.copyfile(final_mp4, gallery_dest)
                print(f"  📱 Video copiado a tu Galería: {gallery_dest}")
            except Exception:
                pass

        # Limpieza de temporales si se solicita
        if cleanup:
            print("  🧹 Limpiando clips temporales intermedios para ahorrar espacio...")
            for vp in video_paths:
                if os.path.exists(vp) and vp != final_mp4:
                    try:
                        os.remove(vp)
                    except Exception:
                        pass

        # ---------------------------------------------------------
        # 6. Auto-Publicación con Webhook de Make / Metricool
        # ---------------------------------------------------------
        print("\n🚀 Verificando auto-publicación a redes sociales...")
        pub_res = server.publish_to_make_webhook(final_mp4, social_kit, project_name)
        print(f"  {pub_res}")

    print(f"\n=======================================================")
    print(f"🎉 ¡PROCESO COMPLETADO EXITOSAMENTE!")
    print(f"📁 Proyecto: {project_dir}")
    print(f"📦 Kit para Redes Sociales:")
    print(f"   📌 Título: {social_kit.get('title')}")
    print(f"   📝 Descripción: {social_kit.get('description')}")
    print(f"   🏷️ TikTok Hashtags: {' '.join(social_kit.get('tiktok_hashtags', []))}")
    print(f"   🏷️ YouTube Tags: {', '.join(social_kit.get('youtube_tags', [])[:8])}...")
    print(f"   💬 Primer Comentario: {social_kit.get('first_comment')}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador de Video Automatizado Zero-Touch MCP")
    parser.add_argument("--topic", default=None, help="Tema para generar guión y escenas con Gemini")
    parser.add_argument("--name", default=None, help="Nombre del proyecto (ej: pilares_01_perceptron)")
    parser.add_argument("--text", default=None, help="Texto del guión proveniente de 'guion osc tiktok'")
    parser.add_argument("--text-file", default=None, help="Ruta a un archivo .txt con el guión completo")
    parser.add_argument("--prompt", nargs="+", default=None, help="Prompt(s) visuales para Google Veo (opcional)")
    parser.add_argument("--music", default=None, help="Ruta a archivo MP3 de música de fondo (opcional)")
    parser.add_argument("--count", type=int, default=1, help="Número de videos completos a generar automáticamente en lote")
    parser.add_argument("--render-ffmpeg", action="store_true", default=True, help="Renderizar video final con FFmpeg (por defecto: True)")
    parser.add_argument("--no-render", action="store_true", help="Desactivar renderizado final de FFmpeg (solo CapCut)")
    parser.add_argument("--cleanup", action="store_true", help="Eliminar clips temporales intermedios tras renderizar")
    parser.add_argument("--force", action="store_true", help="Forzar re-generación completa de audio y video ignorando la caché")
    parser.add_argument("--dry-run", action="store_true", help="Modo prueba sin consumir créditos de API")

    args = parser.parse_args()
    render_flag = False if args.no_render else True

    for video_num in range(args.count):
        project_name = args.name
        raw_text = args.text
        prompts = args.prompt
        social_kit = None

        # Si se pasa un archivo de texto con el guión
        if args.text_file and os.path.exists(args.text_file):
            with open(args.text_file, "r", encoding="utf-8") as f:
                raw_text = f.read().strip()
            if not project_name:
                project_name = Path(args.text_file).stem

        # Caso 1: El usuario pasó su propio guión (de 'guion osc tiktok')
        if raw_text:
            parsed = server.parse_script_and_social_kit(raw_text)
            clean_script = parsed["clean_script"]
            
            if parsed.get("title"):
                social_kit = {
                    "title": parsed["title"],
                    "description": parsed["description"],
                    "tiktok_hashtags": parsed["tiktok_hashtags"],
                    "youtube_tags": parsed["youtube_tags"],
                    "first_comment": parsed["first_comment"]
                }
            
            if not project_name:
                project_name = f"proyecto_tiktok_{video_num+1}" if args.count > 1 else "proyecto_tiktok"
            
            if not prompts:
                print(f"\n🧠 Analizando guión para extraer escenas visuales cinematográficas con Gemini...")
                prompts = server.generate_scenes_from_script(clean_script)
                print(f"  🎬 Escenas extraídas ({len(prompts)}):")
                for i, p in enumerate(prompts):
                    print(f"     [{i+1}] {p}")
            
            script_text = clean_script

        # Caso 2: El usuario pasó un tema específico
        elif args.topic:
            print(f"\n🧠 Generando guión 'guion osc tiktok' y escenas con Gemini para: \"{args.topic}\"...")
            gemini_data = server.generate_script_and_scenes_gemini(args.topic)
            if not project_name:
                project_name = gemini_data.get("project_name", f"video_gemini_{video_num+1}")
            script_text = gemini_data.get("script", "")
            if not prompts:
                prompts = gemini_data.get("scenes", [])
            
            print(f"  📝 Guión generado:\n     \"{script_text}\"")
            print(f"  🎬 Escenas generadas ({len(prompts)}):")
            for i, p in enumerate(prompts):
                print(f"     [{i+1}] {p}")

        # Caso 3 (ZERO-TOUCH TOTAL): Generación autónoma
        else:
            if args.count > 1:
                print(f"\n=======================================================")
                print(f"🤖 GENERANDO VIDEO AUTOMÁTICO ({video_num+1}/{args.count})")
                print(f"=======================================================")
            else:
                print(f"\n🤖 MODO AUTOMÁTICO TOTAL ZERO-TOUCH INICIADO")
            
            auto_topic = server.generate_viral_topic_idea()
            print(f"🔥 Idea viral descubierta: \"{auto_topic}\"")
            
            gemini_data = server.generate_script_and_scenes_gemini(auto_topic)
            if not project_name:
                project_name = gemini_data.get("project_name", f"auto_video_{video_num+1}")
            script_text = gemini_data.get("script", "")
            prompts = gemini_data.get("scenes", [])
            
            print(f"  📝 Guión 'guion osc tiktok':\n     \"{script_text}\"")
            print(f"  🎬 Escenas Veo 9:16 ({len(prompts)}):")
            for i, p in enumerate(prompts):
                print(f"     [{i+1}] {p}")

        prompts_list = prompts if isinstance(prompts, list) else [prompts]

        run_pipeline(
            project_name=project_name,
            script_text=script_text,
            video_prompts=prompts_list,
            bg_music_path=args.music,
            social_kit=social_kit,
            render_ffmpeg=render_flag,
            cleanup=args.cleanup,
            force=args.force,
            dry_run=args.dry_run
        )

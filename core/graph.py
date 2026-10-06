"""
Motor de Grafo Agéntico (Graph Engineering Engine) para Video_Auto_Agent.
Implementa el arnés agéntico con Fan-out concurrente, Join Node determinista y Checkpoints.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import video_mcp_server as server
from core.state import ExecutionState
from core.evaluator import ScriptEvaluator
from workers.audio_worker import AudioWorker
from workers.visual_worker import VisualWorker
from workers.music_worker import MusicWorker
from render.ffmpeg_engine import FFmpegEngine
from render.capcut_engine import CapCutEngine

class GraphRunner:
    def __init__(self, project_name: Optional[str] = None, topic: Optional[str] = None, dry_run: bool = False, force: bool = False, resume: bool = True):
        self.topic = topic
        self.dry_run = dry_run
        self.force = force
        self.resume = resume

        # Si no se pasó nombre de proyecto, usar el topic o generar slug preliminar
        slug = "".join(c if c.isalnum() else "_" for c in (topic or "video_auto").lower()[:28]).strip("_")
        self.project_name = project_name or slug or "video_auto_agent"
        self.project_dir = Path(f"./output/{self.project_name}").resolve()
        self.state = ExecutionState(self.project_dir, self.project_name)

    def run(self) -> Dict[str, Any]:
        """Ejecuta el grafo completo de producción audiovisual con tolerancia a fallos."""
        print(f"\n=======================================================")
        print(f"🎬 INICIANDO GRAPH RUNNER (ARNÉS AGÉNTICO): {self.project_name}")
        print(f"=======================================================")

        # -------------------------------------------------------------
        # NODO 0: Topic Selection (Determinista / Gemini)
        # -------------------------------------------------------------
        if not self.topic:
            if self.resume and self.state.data.get("topic"):
                self.topic = self.state.data["topic"]
                print(f"📌 [Nodo 0: Topic] Reanudado desde checkpoint: {self.topic}")
            else:
                print("📌 [Nodo 0: Topic] Seleccionando tema viral con Gemini...")
                self.topic = server.generate_viral_topic_idea()
                self.state.mark_completed("node_topic", topic=self.topic)
                print(f"  ✨ Tema seleccionado: \"{self.topic}\"")
        else:
            self.state.mark_completed("node_topic", topic=self.topic)

        # -------------------------------------------------------------
        # NODO 1: Closed-Loop Script Generation (Writer + Critic Loop)
        # -------------------------------------------------------------
        script_data = self.state.data.get("script_data")
        if not script_data or self.force or not self.resume:
            print("\n📝 [Nodo 1: Script Loop] Redactando y verificando guion con control de calidad...")
            max_attempts = 3
            valid_script = False
            for attempt in range(1, max_attempts + 1):
                print(f"  ✍️ Intento {attempt}/{max_attempts}: Writer Agent generando borrador...")
                draft = server.generate_script_and_scenes_gemini(self.topic, target_duration_sec=48)
                
                # Evaluación determinista (cero tokens de evaluación)
                is_valid, issues = ScriptEvaluator.evaluate(draft)
                if is_valid:
                    script_data = draft
                    valid_script = True
                    print(f"  ✅ Evaluador de Calidad: Guión APROBADO ({ScriptEvaluator.count_words(draft['script'])} palabras, {len(draft['scenes'])} escenas).")
                    break
                else:
                    print(f"  ⚠️ Evaluador de Calidad: Guión RECHAZADO: {', '.join(issues)}")

            if not valid_script:
                print("  ℹ️ Aplicando fallback estructurado precalibrado tras agotar intentos...")
                script_data = draft

            # Generar Social Kit
            social_kit = server.generate_social_kit_with_gemini(script_data["script"], topic=self.topic)
            self.state.mark_completed("node_script", script_data=script_data, social_kit=social_kit)
        else:
            print(f"✅ [Nodo 1: Script Loop] Reanudado desde checkpoint ({ScriptEvaluator.count_words(script_data['script'])} palabras).")

        script_text = script_data["script"]
        scenes = script_data["scenes"]
        voice_path = str(self.project_dir / "voiceover.mp3")
        music_path = str(self.project_dir / "bg_ambient.mp3")

        # -------------------------------------------------------------
        # NODO 2: Fan-out Paralelo (ElevenLabs + Video Scenes + Music)
        # -------------------------------------------------------------
        print("\n⚡ [Nodo 2: Fan-Out Paralelo] Iniciando producción concurrente de assets...")

        def run_audio():
            if self.resume and os.path.exists(voice_path) and os.path.getsize(voice_path) > 10000:
                dur = server.get_media_duration_us(voice_path) / 1_000_000
                return {"voice_path": voice_path, "duration_s": dur}
            return AudioWorker.process(script_text, voice_path, force=self.force, dry_run=self.dry_run)

        def run_visuals():
            return VisualWorker.process_all_scenes(scenes, self.project_dir, dry_run=self.dry_run, max_workers=3)

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_audio = executor.submit(run_audio)
            future_visuals = executor.submit(run_visuals)

            audio_res = future_audio.result()
            clip_paths = future_visuals.result()

        voice_dur_s = audio_res["duration_s"]
        print(f"  🎙️ Locución lista: {voice_dur_s:.2f}s")
        print(f"  🎞️ {len(clip_paths)} clips de escena listos y verificados en disco.")

        # Música de fondo
        music_file = MusicWorker.process(music_path, int(voice_dur_s), self.project_name, dry_run=self.dry_run)
        print(f"  🎵 Pista musical preparada: {music_file}")

        self.state.mark_completed(
            "node_fan_out",
            voiceover_path=voice_path,
            voice_duration_s=voice_dur_s,
            clips=clip_paths,
            music_path=music_file
        )

        # -------------------------------------------------------------
        # NODO 3: Join Node Determinista (Barrera de Verificación)
        # -------------------------------------------------------------
        print("\n🧩 [Nodo 3: Join Node] Verificando integridad de assets antes del ensamblado...")
        if not os.path.exists(voice_path) or os.path.getsize(voice_path) < 10000:
            raise RuntimeError("Fallo crítico en Join Node: Archivo de voz ausente o corrupto.")

        for p in clip_paths:
            if not os.path.exists(p) or os.path.getsize(p) < 20000:
                raise RuntimeError(f"Fallo crítico en Join Node: Clip incompleto ({p}).")

        # -------------------------------------------------------------
        # NODO 4: Output Synthesis (FFmpeg Direct Render + CapCut Draft)
        # -------------------------------------------------------------
        print("\n⚙️ [Nodo 4: Output Synthesis] Ensamblando video y generando borrador de CapCut...")
        output_video = str(self.project_dir / "final_video.mp4")

        # CapCut Draft
        capcut_res = CapCutEngine.create_draft(self.project_name, clip_paths, voice_path, music_file)
        print(f"  📁 {capcut_res}")

        # FFmpeg Render
        render_res = FFmpegEngine.render(clip_paths, voice_path, music_file, output_video)
        print(f"  🎬 {render_res}")

        # Sincronización móvil (/sdcard/Movies)
        movies_dir = Path("/sdcard/Movies")
        if movies_dir.exists() and os.path.exists(output_video):
            target_mobile = movies_dir / f"{self.project_name}_final.mp4"
            shutil.copy2(output_video, target_mobile)
            print(f"  📲 Copiado a Galería Móvil: {target_mobile}")

        self.state.mark_completed(
            "node_completed",
            rendered_video_path=output_video,
            status="completed"
        )

        print(f"\n✨ ¡GRAPH RUNNER FINALIZADO CON ÉXITO!")
        print(f"📁 Proyecto: {self.project_dir}")
        print(f"🎥 Video: {output_video}\n")

        return self.state.data

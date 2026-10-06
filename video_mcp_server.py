#!/usr/bin/env python3
"""
Servidor MCP para Automatización de Contenido Audiovisual:
- Generación de voz con ElevenLabs y truncado automático de silencios (FFmpeg).
- Generación de video con Google AI Studio (Veo 2.0 / 9:16).
- Creación de borrador de proyecto editable en CapCut con pistas y volúmenes (Voz 100%, Música 7%).
- Renderizado directo opcional mediante FFmpeg optimizado para móviles.
"""

import os
import sys
import json
import time
import uuid
import re
import random
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
import requests

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

try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("video-automation-pipeline")
except ImportError:
    # Soporte para ejecución standalone / testing antes de compilar FastMCP
    class DummyMCP:
        def tool(self):
            def decorator(fn):
                return fn
            return decorator
        def run(self):
            print("Servidor MCP: FastMCP no está disponible en este momento. Ejecuta 'pip install mcp' para habilitar el transporte MCP.")
    mcp = DummyMCP()


# ==========================================
# UTILIDADES DE AUDIO Y VIDEO
# ==========================================

def get_media_duration_us(file_path: str) -> int:
    """Devuelve la duración exacta de un archivo en microsegundos usando ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return int(float(res.stdout.strip()) * 1_000_000)
    except Exception:
        return 5_000_000  # Valor por defecto: 5 segundos


def trim_dead_silence(
    input_path: str,
    output_path: str,
    max_pause_sec: float = 0.4,
    threshold_db: int = -40
):
    """Elimina silencios muertos de la locución mediante filtro silenceremove de FFmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af",
        f"silenceremove=stop_periods=-1:stop_duration={max_pause_sec}:stop_threshold={threshold_db}dB",
        output_path
    ]
    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True
    )


def clean_script_tags(text: str) -> str:
    """Elimina etiquetas de dirección actoral como [Conversational], [Warm], [Newsreader], etc."""
    cleaned = re.sub(r'\[[A-Za-z0-9_\-\s]+\]', '', text)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return " ".join(lines)


def parse_script_and_social_kit(raw_text: str) -> Dict[str, Any]:
    """
    Analiza la salida completa generada por 'guion osc tiktok'.
    Extrae la locución limpia para ElevenLabs, el título, descripción, hashtags y primer comentario.
    """
    result = {
        "clean_script": "",
        "title": "",
        "description": "",
        "tiktok_hashtags": [],
        "youtube_tags": [],
        "first_comment": ""
    }

    social_section = ""
    script_section = raw_text
    
    if "Kit para Redes Sociales" in raw_text or "Kit para redes" in raw_text.lower():
        parts = re.split(r'Kit para [Rr]edes [Ss]ociales:?', raw_text, maxsplit=1)
        script_section = parts[0]
        social_section = parts[1] if len(parts) > 1 else ""

    # Extraer campos de redes sociales si están presentes
    if social_section:
        title_match = re.search(r'[\*\-]?\s*T[íi]tulo:\s*(.+)', social_section, re.IGNORECASE)
        if title_match:
            result["title"] = title_match.group(1).strip().strip('*').strip()

        desc_match = re.search(r'[\*\-]?\s*Descripci[óo]n\s*(?:breve)?:\s*(.+)', social_section, re.IGNORECASE)
        if desc_match:
            result["description"] = desc_match.group(1).strip().strip('*').strip()

        tt_match = re.search(r'[\*\-]?\s*(?:\d+\s*)?Hashtags\s*(?:para\s*TikTok)?:\s*(.+)', social_section, re.IGNORECASE)
        if tt_match:
            tags = re.findall(r'#\w+', tt_match.group(1))
            result["tiktok_hashtags"] = tags if tags else [t.strip() for t in tt_match.group(1).split() if t.strip()]

        yt_match = re.search(r'[\*\-]?\s*(?:\d+\s*)?Tags\s*(?:para\s*YouTube\s*Shorts)?\s*(?:\([^)]*\))?:\s*(.+)', social_section, re.IGNORECASE)
        if yt_match:
            raw_yt = yt_match.group(1).strip()
            result["youtube_tags"] = [t.strip().strip('*').strip() for t in raw_yt.split(',') if t.strip()]

        comment_match = re.search(r'[\*\-]?\s*Primer\s*comentario\s*(?:TikTok)?\s*(?:\([^)]*\))?:\s*(?:>\s*)?([^\n]+)', social_section, re.IGNORECASE)
        if not comment_match:
            comment_match = re.search(r'Primer\s*comentario[^\n]*\n\s*>\s*([^\n]+)', social_section, re.IGNORECASE)
        if comment_match:
            raw_c = comment_match.group(1).strip().strip('>').strip()
            # Quitar cualquier mención de conteo de caracteres al final como (139 caracteres)
            raw_c = re.sub(r'\s*\(\d+\s*caracteres\)$', '', raw_c)
            result["first_comment"] = raw_c.strip()

    # Si hay bloques de GUION VIRAL
    if "GUION VIRAL:" in script_section or "GUION VIRAL" in script_section:
        guion_parts = re.split(r'GUION VIRAL:?', script_section)
        target_script = guion_parts[-1]
        if "Configuración ElevenLabs:" in target_script or "Configuracion ElevenLabs:" in target_script:
            target_script = re.split(r'Configuraci[óo]n ElevenLabs:.*?\n(?=\[|[A-Z¿¡])', target_script, flags=re.DOTALL)[-1]
        result["clean_script"] = clean_script_tags(target_script)
    else:
        result["clean_script"] = clean_script_tags(script_section)

    return result


@mcp.tool()
def generate_social_kit_with_gemini(script_text: str, topic: str = "") -> Dict[str, Any]:
    """
    Genera automáticamente el Kit completo de Redes Sociales (Título viral, descripción corta,
    5 hashtags para TikTok, 20 tags para YouTube Shorts y primer comentario) usando Gemini.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    default_kit = {
        "title": topic or "El Secreto Oculto de la Tecnología ⚡",
        "description": f"{script_text[:90]}...",
        "tiktok_hashtags": ["#InteligenciaArtificial", "#AprendeEnTikTok", "#TechHistory", "#Misterios", "#Viral"],
        "youtube_tags": ["Shorts", "Inteligencia Artificial", "Tecnologia", "Historia", "Misterio", "Documental", "Curiosidades", "Ciencia", "Futuro", "Innovacion", "Algoritmos", "Computacion", "Datos", "Descubrimientos", "Tendencias", "Aprende", "Educacion", "ShortsViral", "YouTubeShorts", "Tech"],
        "first_comment": "Conoce más historias y proyectos tecnológicos en el enlace de mi perfil 🚀"
    }

    if not api_key or api_key == "tu_clave_de_google_ai_studio_aqui":
        return default_kit

    candidate_models = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    prompt = (
        "A partir del siguiente guión para video vertical, genera el Kit para Redes Sociales optimizado para viralidad. "
        "Devuelve estrictamente un JSON válido con estas claves exactas: "
        "'title' (título llamativo con 1 emoji), "
        "'description' (descripción breve de máximo 100 caracteres), "
        "'tiktok_hashtags' (arreglo con exactamente 5 hashtags con #), "
        "'youtube_tags' (arreglo con exactamente 20 tags relevantes para YouTube Shorts), "
        "'first_comment' (primer comentario para fijar con CTA de menos de 140 caracteres)."
    )
    payload = {
        "system_instruction": {"parts": [{"text": prompt}]},
        "contents": [{"parts": [{"text": f"Guión:\n{script_text}"}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.7}
    }

    for model in candidate_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
            if res.status_code == 200:
                res_json = res.json()
                raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
        except Exception:
            continue
    return default_kit


@mcp.tool()
def publish_to_make_webhook(
    video_path: str,
    social_kit: Dict[str, Any],
    project_name: str
) -> str:
    """
    Envía automáticamente el video renderizado y todos los metadatos del social_kit
    a un Webhook de Make.com o Metricool para auto-publicación en redes sociales.
    """
    webhook_url = os.environ.get("MAKE_WEBHOOK_URL") or os.environ.get("METRICOOL_WEBHOOK_URL")
    if not webhook_url or webhook_url.startswith("tu_webhook"):
        return "Auto-publicación omitida: MAKE_WEBHOOK_URL no configurada en .env."

    try:
        payload = {
            "event": "video_ready_to_publish",
            "project_name": project_name,
            "video_file_path": os.path.abspath(video_path),
            "video_file_name": os.path.basename(video_path),
            "title": social_kit.get("title", project_name),
            "description": social_kit.get("description", ""),
            "tiktok_hashtags": social_kit.get("tiktok_hashtags", []),
            "tiktok_hashtags_str": " ".join(social_kit.get("tiktok_hashtags", [])),
            "youtube_tags": social_kit.get("youtube_tags", []),
            "youtube_tags_str": ", ".join(social_kit.get("youtube_tags", [])),
            "first_comment": social_kit.get("first_comment", ""),
            "timestamp": int(time.time())
        }

        res = requests.post(webhook_url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        if res.status_code in (200, 201, 204):
            return f"✅ Publicación enviada con éxito a Make.com/Metricool (Status {res.status_code})"
        else:
            return f"⚠️ Webhook respondió con status {res.status_code}: {res.text[:150]}"
    except Exception as e:
        return f"❌ Error enviando a Webhook de Make.com: {str(e)}"


@mcp.tool()
def generate_background_music_treblo(
    prompt: str,
    output_path: str,
    duration_sec: int = 45
) -> str:
    """
    Genera una pista de música instrumental de fondo usando la API de Treblo.com (Melodia v3).
    """
    api_key = os.environ.get("TREBLO_API_KEY")
    if not api_key or api_key.startswith("tu_clave"):
        return "TREBLO_API_KEY no configurada."

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt or "ambient cinematic instrumental synth pads background music",
            "instrumental": True
        }
        res = requests.post("https://api.treblo.com/v1/generations/v3", json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            task_id = res.json().get("task_id")
            if task_id:
                for _ in range(24):
                    time.sleep(5)
                    st_resp = requests.get(f"https://api.treblo.com/v1/generations/status/{task_id}", headers=headers, timeout=15)
                    if st_resp.status_code == 200 and st_resp.json().get("status") == "SUCCESS":
                        final_res = requests.get(f"https://api.treblo.com/v1/generations/{task_id}", headers=headers, timeout=15)
                        audio_url = final_res.json().get("audio_url")
                        if audio_url:
                            aud_data = requests.get(audio_url, timeout=30)
                            if aud_data.status_code == 200:
                                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                                with open(output_path, "wb") as f:
                                    f.write(aud_data.content)
                                return f"Música instrumental generada con éxito con Treblo en: {output_path}"
            return "No se completó la tarea de generación de Treblo a tiempo."
        elif res.status_code == 402:
            return "Créditos de Treblo agotados (402). Usando generador instrumental ambiental."
        else:
            return f"Error de Treblo API ({res.status_code}): {res.text[:150]}"
    except Exception as e:
        return f"Error conectando con Treblo: {str(e)}"


# ==========================================
# HERRAMIENTAS MCP
# ==========================================

@mcp.tool()
def generate_voiceover_elevenlabs(
    text: str,
    output_path: str,
    voice_id: str = "TX3LPaxmHKxFdv7VOQHJ",  # Liam - Energetic, Social Media Creator
    model_id: str = "eleven_multilingual_v2",
    trim_silence: bool = True,
    force_refresh: bool = False
) -> str:
    """
    Genera audio de voz con ElevenLabs a partir de un texto, aplica truncado automático
    de silencios muertos y guarda el archivo en el disco.
    Incluye protección de tokens mediante caché SHA-256 para no consumir créditos si el texto no cambió.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # 1. Protección de tokens con Hash SHA-256
    cache_dir = Path(__file__).parent / "cache" / "tts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tts_hash = hashlib.sha256(f"{text.strip()}_{voice_id}_{model_id}".encode("utf-8")).hexdigest()
    cached_file = cache_dir / f"{tts_hash}.mp3"
    
    if not force_refresh:
        # A. Si el archivo destino ya existe y tiene duración válida
        if os.path.exists(output_path) and get_media_duration_us(output_path) > 1_000_000:
            if not cached_file.exists():
                try:
                    shutil.copyfile(output_path, cached_file)
                except Exception:
                    pass
            return f"⚡ Audio reutilizado de archivo existente (0 tokens consumidos) en: {output_path}"
            
        # B. Si existe en la caché central
        if cached_file.exists() and cached_file.stat().st_size > 1000:
            try:
                shutil.copyfile(cached_file, output_path)
                return f"⚡ Audio recuperado de caché SHA-256 (0 tokens consumidos) en: {output_path}"
            except Exception:
                pass

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return "Error: La variable de entorno ELEVENLABS_API_KEY no está configurada."

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.2
        }
    }

    raw_output = output_path + ".raw.mp3" if trim_silence else output_path

    # Reintentos con backoff para conexión resiliente en móviles
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            if response.status_code == 200:
                with open(raw_output, "wb") as f:
                    f.write(response.content)

                if trim_silence:
                    try:
                        trim_dead_silence(raw_output, output_path)
                        if os.path.exists(raw_output):
                            os.remove(raw_output)
                    except Exception as e:
                        return f"Audio generado pero falló el truncado con FFmpeg: {str(e)}"

                # Guardar en caché central para futuras reutilizaciones (0 tokens)
                if os.path.exists(output_path):
                    try:
                        shutil.copyfile(output_path, cached_file)
                    except Exception:
                        pass

                return f"Audio generado con éxito con voz Liam y silencios truncados en: {output_path}"
            elif response.status_code == 429:
                time.sleep(3 + attempt * 2)
            else:
                if attempt == 2:
                    return f"Error de ElevenLabs ({response.status_code}): {response.text}"
                time.sleep(2)
        except Exception as e:
            if attempt == 2:
                return f"Error conectando con ElevenLabs tras 3 intentos: {str(e)}"
            time.sleep(3)

    return f"Error conectando con ElevenLabs: no se pudo generar el audio."


@mcp.tool()
def generate_viral_topic_idea() -> str:
    """
    Genera automáticamente una idea o tema altamente viral de misterio, tecnología oscura,
    historias olvidadas o conspiraciones reales para TikTok/Shorts/Reels.
    Evita generar temas repetidos usando el historial persistente en .history_topics.json.
    """
    history_file = Path(__file__).parent / ".history_topics.json"
    used_topics = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                used_topics = json.load(f)
        except Exception:
            used_topics = []

    api_key = os.environ.get("GEMINI_API_KEY")
    fallback_topics = [
        "El misterio del Perceptrón y la muerte de Frank Rosenblatt",
        "La torre Wardenclyffe de Nikola Tesla y la energía inalámbrica libre",
        "El experimento de Filadelfia y la teletransportación de buques de guerra",
        "El misterio del submarino soviético K-129 y el Proyecto Azorian",
        "El código prohibido de la biblioteca secreta del Vaticano",
        "La conspiración del cártel Phoebus y la bombilla de luz eterna",
        "El proyecto Stargate y la visión remota de la CIA",
        "El enigma del manuscrito Voynich y los códigos botánicos perdidos",
        "La ciudad subterránea de Derinkuyu y el refugio antiaéreo antiguo",
        "El pozo superprofundo de Kola y las grabaciones prohibidas a 12 km"
    ]
    
    available_fallbacks = [t for t in fallback_topics if t not in used_topics]
    if not available_fallbacks:
        available_fallbacks = fallback_topics

    if not api_key or api_key == "tu_clave_de_google_ai_studio_aqui":
        chosen = random.choice(available_fallbacks)
        used_topics.append(chosen)
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(used_topics[-50:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return chosen

    candidate_models = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    avoid_str = f"NO repitas ninguno de los siguientes temas que ya se usaron antes: {', '.join(used_topics[-15:])}" if used_topics else ""
    payload = {
        "contents": [{"parts": [{"text": f"Genera 1 solo tema nuevo, corto e intrigante de misterio, tecnología prohibida, experimentos oscuros o historia secreta ideal para un video viral de TikTok de alto impacto. {avoid_str}. Devuelve ÚNICAMENTE el título/tema en 1 línea, sin comillas ni texto extra."}]}],
        "generationConfig": {"temperature": 0.9}
    }

    for model in candidate_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
            if res.status_code == 200:
                idea = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                chosen = idea if len(idea) > 5 else random.choice(available_fallbacks)
                used_topics.append(chosen)
                try:
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump(used_topics[-50:], f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                return chosen
        except Exception:
            continue

    chosen = random.choice(available_fallbacks)
    used_topics.append(chosen)
    return chosen


@mcp.tool()
def generate_script_and_scenes_gemini(
    topic: str,
    target_duration_sec: int = 48
) -> dict:
    """
    Usa Gemini para generar un guión narrativo viral en español con la fórmula exacta de 'guion osc tiktok'
    y desglosarlo en 5-6 escenas con prompts cinematográficos 9:16 optimizados para video vertical.
    Estándar estricto de duración: 40 a 55 segundos (110 a 130 palabras).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    safe_name = "".join(c if c.isalnum() else "_" for c in topic.lower()[:30]).strip("_")

    default_fallback_script = (
        f"¿Y si todo lo que nos contaron sobre {topic} fuera solo la mitad de la historia? "
        "En los archivos clasificados de mediados del siglo veinte, un equipo de científicos documentó anomalías que la historia oficial decidió borrar. "
        "Al principio parecía un avance prometedor, pero al profundizar descubrieron patrones que desafiaban las leyes de la física. "
        "Los informes fueron sellados bajo estricto secreto de estado y los involucrados recibieron órdenes de guardar silencio absoluto. "
        "Hoy, los mismos datos filtrados demuestran que el fenómeno sigue activo y operando entre nosotros. "
        "¿Crees que algún día revelarán toda la verdad o seguirá oculto para siempre? ¡Comenta tu opinión!"
    )
    default_fallback_scenes = [
        f"Vertical 9:16, cinematic mysterious archive room, classified vintage folders, dimly lit desk, moody atmosphere, 8k",
        f"Vertical 9:16, cinematic secret laboratory, retro analog monitors flickering, scientists looking concerned, 8k",
        f"Vertical 9:16, cinematic intense close up, glowing ancient and technological anomaly, deep shadows, 8k",
        f"Vertical 9:16, cinematic sprawling underground concrete bunker, rusted machinery, unnatural pulsing light, 8k",
        f"Vertical 9:16, cinematic glowing futuristic digital network expanding across Earth map, epic climax lighting, 8k"
    ]

    if not api_key or api_key == "tu_clave_de_google_ai_studio_aqui":
        return {
            "project_name": safe_name or "video_proyecto",
            "title": topic,
            "script": default_fallback_script,
            "scenes": default_fallback_scenes
        }

    candidate_models = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    system_instruction = (
        "Eres el creador y guionista estrella del canal 'guion osc tiktok', experto en retención del 100% en videos cortos de TikTok, Reels y Shorts. "
        "Tu estilo es: narración cinematográfica de misterio, tecnología inquietante, conspiraciones y eventos históricos fascinantes. "
        "\nESTÁNDAR OBLIGATORIO DE DURACIÓN (40 a 55 SEGUNDOS): "
        "El guión debe tener OBLIGATORIAMENTE entre 110 y 130 palabras exactas (duración hablada de 42 a 52 segundos a ritmo dinámico). "
        "\nEstructura obligatoria del guión: "
        "1. Gancho demoledor (0-3 seg): Pregunta o afirmación impactante que detenga el scroll al instante. "
        "2. Contexto y desarrollo acelerado (4-20 seg): Detalles históricos o tecnológicos precisos y tensos. "
        "3. Giro / Conflicto inquietante (21-40 seg): Datos ocultos, paradojas o anomalías que aumentan la tensión. "
        "4. Clímax final perturbador (41-50 seg): La conclusión que hiela la sangre. "
        "5. Pregunta/CTA de cierre (51-55 seg): Pregunta intrigante para generar comentarios. "
        "\nAdemás, debes desglosar la historia en exactamente 5 o 6 escenas visuales continuas, redactando para cada una un prompt en inglés hiper-detallado para video 9:16 (siempre iniciando con 'Vertical 9:16, cinematic...'). "
        "Devuelve estrictamente un JSON válido con las siguientes claves: "
        "'project_name' (slug corto en minúsculas y guiones bajos sin caracteres especiales, ej: misterio_voynich), "
        "'title' (título llamativo con emoji para TikTok), "
        "'script' (texto continuo y fluido de 110 a 130 palabras en español sin etiquetas de dirección), "
        "'scenes' (lista de 5 a 6 strings con los prompts en inglés para 9:16)."
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [{"text": f"Tema del video: {topic}"}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.75
        }
    }

    for model in candidate_models:
        for attempt in range(2):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if response.status_code == 200:
                    res_json = response.json()
                    raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(raw_text)
                    raw_pname = data.get("project_name", safe_name)
                    data["project_name"] = "".join(c if c.isalnum() else "_" for c in raw_pname.lower()[:35]).strip("_")
                    return data
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
                else:
                    break
            except Exception:
                time.sleep(1)

    return {
        "project_name": safe_name or "video_proyecto",
        "title": topic,
        "script": default_fallback_script,
        "scenes": default_fallback_scenes
    }


@mcp.tool()
def generate_scenes_from_script(
    script_text: str
) -> List[str]:
    """
    Analiza un guión en español proporcionado por el usuario y genera automáticamente 4-5 prompts
    cinematográficos en inglés optimizados para Google Veo 2.0 (Vertical 9:16).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    default_scenes = [
        "Vertical 9:16, cinematic atmosphere, moody lighting, intense documentary style, 8k",
        "Vertical 9:16, close up dramatic shot, detailed textures, cinematic composition, 8k",
        "Vertical 9:16, dramatic shadows, mysterious atmosphere, atmospheric haze, 8k",
        "Vertical 9:16, wide angle epic ending visual, glowing dynamic lights, 8k"
    ]
    if not api_key or api_key == "tu_clave_de_google_ai_studio_aqui":
        return default_scenes

    candidate_models = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    system_instruction = (
        "Eres un director de fotografía cinematográfica para videos verticales (TikTok, Reels, Shorts). "
        "Lee el siguiente guión en español y divídelo en 4 o 5 escenas visuales continuas que acompañen el relato. "
        "Escribe para cada escena un prompt en inglés detallado para Google Veo 2.0 (debe incluir 'Vertical 9:16, cinematic...'). "
        "Devuelve estrictamente un arreglo JSON de strings: ['Vertical 9:16...', 'Vertical 9:16...']."
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [{"text": f"Guión:\n{script_text}"}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.7
        }
    }

    for model in candidate_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            if response.status_code == 200:
                res_json = response.json()
                raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                scenes = json.loads(raw_text)
                if isinstance(scenes, list) and len(scenes) > 0:
                    return scenes
        except Exception:
            continue
    return default_scenes


@mcp.tool()
def generate_video_clip_veo(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Genera un clip de video usando el modelo Veo en Google AI Studio con la relación de aspecto 9:16.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: La variable de entorno GEMINI_API_KEY no está configurada."

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/veo-3.1-fast-generate-preview:predictLongRunning?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "aspectRatio": aspect_ratio,
                "sampleCount": 1
            }
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        if res.status_code == 200:
            data = res.json()
            # Si devuelve operación asíncrona, esperar resultado
            op_name = data.get("name")
            if op_name:
                for _ in range(30):
                    time.sleep(5)
                    poll_url = f"https://generativelanguage.googleapis.com/v1beta/{op_name}?key={api_key}"
                    poll_res = requests.get(poll_url, timeout=30)
                    if poll_res.status_code == 200 and poll_res.json().get("done"):
                        res_data = poll_res.json().get("response", {})
                        video_uri = res_data.get("generatedVideos", [{}])[0].get("video", {}).get("uri")
                        if video_uri:
                            vid_resp = requests.get(video_uri, timeout=60)
                            if vid_resp.status_code == 200:
                                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                                with open(output_path, "wb") as f:
                                    f.write(vid_resp.content)
                                return f"Clip de video generado exitosamente en: {output_path}"
            return "No se pudo obtener el archivo de video de la respuesta de Veo."
        elif res.status_code == 429:
            return "Cuota de Veo 3.1 no disponible o requiere plan de facturación habilitado en Google AI Studio (429)."
        else:
            return f"Error de Veo API ({res.status_code}): {res.text[:200]}"
    except Exception as e:
        return f"Error conectando con Veo API: {str(e)}"


@mcp.tool()
def generate_video_clip_wan(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Genera un clip de video usando el modelo Wan 2.1 a través de Fal.ai o Replicate.
    """
    fal_key = os.environ.get("FAL_KEY")
    replicate_token = os.environ.get("REPLICATE_API_TOKEN")
    
    if fal_key and not fal_key.startswith("tu_clave"):
        try:
            url = "https://fal.run/fal-ai/wan-t2v"
            headers = {
                "Authorization": f"Key {fal_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio
            }
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                data = res.json()
                video_url = data.get("video", {}).get("url")
                if video_url:
                    v_res = requests.get(video_url, timeout=60)
                    if v_res.status_code == 200:
                        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(v_res.content)
                        return f"Clip de video generado exitosamente con Wan 2.1 (Fal.ai) en: {output_path}"
            return f"Error en Fal.ai Wan 2.1 ({res.status_code}): {res.text[:150]}"
        except Exception as e:
            return f"Error conectando con Fal.ai Wan 2.1: {str(e)}"
            
    if replicate_token and not replicate_token.startswith("tu_clave"):
        try:
            url = "https://api.replicate.com/v1/models/wan-video/wan-2.1-t2v-1.3b/predictions"
            headers = {
                "Authorization": f"Bearer {replicate_token}",
                "Content-Type": "application/json",
                "Prefer": "wait"
            }
            payload = {
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio
                }
            }
            res = requests.post(url, json=payload, headers=headers, timeout=90)
            if res.status_code in (200, 201):
                data = res.json()
                video_url = data.get("output")
                if isinstance(video_url, list) and video_url:
                    video_url = video_url[0]
                if video_url:
                    v_res = requests.get(video_url, timeout=60)
                    if v_res.status_code == 200:
                        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(v_res.content)
                        return f"Clip de video generado exitosamente con Wan 2.1 (Replicate) en: {output_path}"
            return f"Error en Replicate Wan 2.1 ({res.status_code}): {res.text[:150]}"
        except Exception as e:
            return f"Error conectando con Replicate Wan 2.1: {str(e)}"

    return "No se ha configurado FAL_KEY ni REPLICATE_API_TOKEN en .env."


def _try_fal_ai_video(prompt: str, output_path: str, duration_sec: int, fal_key: str) -> bool:
    """
    Intenta generar un clip de video con IA usando fal.ai (Wan 2.1 14B / MiniMax Hailuo).
    Retorna True si el clip fue generado exitosamente, False en caso contrario.
    Usa curl para la descarga final (compatible con Termux Android).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Modelos a intentar en orden de prioridad (más barato primero)
    fal_endpoints = [
        {
            "url": "https://fal.run/fal-ai/wan/v2.1/t2v-14b",
            "payload": {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "duration": min(duration_sec, 8),
            },
            "name": "Wan 2.1 14B"
        },
        {
            "url": "https://fal.run/fal-ai/wan/v2.1/t2v-1.3b",
            "payload": {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "duration": min(duration_sec, 8),
            },
            "name": "Wan 2.1 1.3B"
        },
        {
            "url": "https://fal.run/fal-ai/minimax-video/text-to-video",
            "payload": {
                "prompt": prompt,
                "prompt_optimizer": True,
            },
            "name": "MiniMax Hailuo"
        },
    ]

    headers_fal = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json"
    }

    for endpoint in fal_endpoints:
        raw_path = output_path + ".fal_raw.mp4"
        try:
            res = requests.post(
                endpoint["url"],
                json=endpoint["payload"],
                headers=headers_fal,
                timeout=180  # Los modelos de IA pueden tardar hasta 3 minutos
            )
            if res.status_code != 200:
                continue

            data = res.json()

            # Extraer URL del video de la respuesta de fal.ai
            video_url = None
            if "video" in data and isinstance(data["video"], dict):
                video_url = data["video"].get("url")
            elif "videos" in data and isinstance(data["videos"], list) and data["videos"]:
                video_url = data["videos"][0].get("url")
            elif "output" in data:
                out = data["output"]
                if isinstance(out, str):
                    video_url = out
                elif isinstance(out, list) and out:
                    video_url = out[0]

            if not video_url:
                continue

            # Descargar con curl (fiable en Termux Android)
            dl_cmd = [
                "curl", "-s", "-L", "--max-time", "120",
                "-A", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                "-o", raw_path, video_url
            ]
            subprocess.run(dl_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 20000):
                continue

            # Normalizar a 1080x1920, 30fps, duración exacta con stream_loop
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", raw_path,
                "-t", str(duration_sec),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                "-r", "30",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-an",
                output_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if os.path.exists(raw_path):
                os.remove(raw_path)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                return True  # Éxito con IA

        except Exception:
            # Limpiar archivo parcial si existe
            if os.path.exists(raw_path):
                os.remove(raw_path)
            continue

    return False  # No se pudo generar con IA


@mcp.tool()
def generate_cinematic_scene_clip(
    prompt: str,
    output_path: str,
    duration_sec: int = 8,
    scene_index: int = 1
) -> str:
    """
    Genera un clip de video vertical 9:16 hiperrealista para una escena.
    Estrategia de cascada:
      1. fal.ai IA (Wan 2.1 / MiniMax Hailuo) — si FAL_KEY está configurada.
      2. Pexels stock video (fallback) — si IA falla o no hay clave.
    Garantiza duración exacta con -stream_loop -1 a 30fps fijos.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # ─────────────────────────────────────────────────────────────
    # PASO 0: Intentar Gemini Omni Flash (Tokens de Google)
    # ─────────────────────────────────────────────────────────────
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        load_dotenv()
        gemini_key = os.environ.get("GEMINI_API_KEY")

    if gemini_key and not gemini_key.startswith("tu_clave"):
        try:
            omni_res = generate_video_clip_omni(prompt, output_path, duration_sec=duration_sec, aspect_ratio="9:16")
            if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                return omni_res
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    # PASO 0.5: Intentar Google Colab GPU propio (Gradio / ComfyUI)
    # ─────────────────────────────────────────────────────────────
    colab_url = os.environ.get("COLAB_API_URL")
    if not colab_url:
        load_dotenv()
        colab_url = os.environ.get("COLAB_API_URL")

    if colab_url and not colab_url.startswith("tu_url"):
        try:
            from workers.colab_worker import ColabWorker
            colab_ok = ColabWorker.generate_video_clip(prompt, output_path, duration_sec=duration_sec)
            if colab_ok and os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                return f"✨ Clip generado con tu Google Colab GPU en: {output_path}"
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    # PASO 1: Intentar fal.ai (video generado por IA real)
    # ─────────────────────────────────────────────────────────────
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        load_dotenv()
        fal_key = os.environ.get("FAL_KEY")

    if fal_key and not fal_key.startswith("tu_clave"):
        ai_ok = _try_fal_ai_video(prompt, output_path, duration_sec, fal_key)
        if ai_ok:
            return f"✨ Clip de video IA (fal.ai) generado en {duration_sec}s: {output_path}"

    # ─────────────────────────────────────────────────────────────
    # PASO 2: Fallback — Pexels stock video
    # ─────────────────────────────────────────────────────────────
    # Palabras no informativas a filtrar
    stop_words = {
        "vertical", "9:16", "cinematic", "8k", "atmosphere", "moody", "shot",
        "close", "up", "with", "from", "and", "the", "lighting", "deep",
        "detailed", "textures", "intense", "looking", "sprawling", "unnatural",
        "pulsing", "expanding", "across", "hd", "4k", "scene", "view", "epic", "climax"
    }
    
    clean_p = re.sub(r'[^a-zA-Z0-9\s]', ' ', prompt.lower())
    clean_words = [w for w in clean_p.split() if len(w) > 2 and w not in stop_words]
    
    # Diccionario de expansión semántica por temas para garantizar variedad sinónima
    synonym_map = {
        "scientist": ["researchers dark room", "investigators archival", "vintage observatory", "analysts computer screens"],
        "scientists": ["researchers looking worried", "investigation archive", "astronomers night telescope", "laboratory technicians"],
        "laboratory": ["secret underground bunker", "vintage science room", "retro analog monitors", "classified document vault"],
        "archive": ["classified library books", "vintage file cabinets", "dusty old documents", "secret evidence records"],
        "ancient": ["mysterious stone ruins", "ancient hieroglyphs carved", "historical relic chamber", "temple dark shadows"],
        "anomaly": ["abstract glowing energy", "unexplained light phenomenon", "pulsing dimensional portal", "cosmic dark matter"],
        "bunker": ["concrete underground tunnel", "dark industrial facility", "rusty abandoned shelter", "secret military corridor"],
        "network": ["digital matrix cyberspace", "global communication satellite", "futuristic server lights", "holographic world data"],
        "computer": ["vintage terminal green phosphor", "dark server racks blinking", "cyber security control room", "hacker dark screen"],
        "technology": ["high tech glowing hardware", "quantum computing chips", "surveillance screens room", "futuristic laboratory"]
    }

    # Fallbacks temáticos rotativos variados
    thematic_fallbacks = [
        ["ancient mystery", "relic chamber", "pyramid shadow", "old artifact"],
        ["secret laboratory", "researcher observatory", "retro computer room", "scientists archive"],
        ["dark bunker", "underground tunnel", "industrial mystery", "abandoned reactor"],
        ["cyber technology", "server room blinking", "matrix digital flow", "hacker terminal"],
        ["digital network map", "satellite earth orbit", "global glowing connection", "cyber telemetry"],
        ["space galaxy anomaly", "deep cosmic nebula", "telescope stars night", "black hole simulation"],
        ["matrix coding", "cyber security monitor", "futuristic circuit board", "abstract dark light"]
    ]

    expanded_synonyms = []
    for w in clean_words:
        if w in synonym_map:
            expanded_synonyms.extend(synonym_map[w])

    queries_to_try = []
    # 1. Sinónimo expandido si coincide con las palabras clave
    if expanded_synonyms:
        random.shuffle(expanded_synonyms)
        queries_to_try.extend(expanded_synonyms[:2])

    # 2. Combinación limpia de palabras originales
    if len(clean_words) >= 2:
        queries_to_try.append(" ".join(clean_words[:2]))
    if len(clean_words) >= 1:
        queries_to_try.append(clean_words[0])

    # 3. Fallbacks temáticos con rotación por escena y aleatoriedad
    theme_group = thematic_fallbacks[(scene_index - 1) % len(thematic_fallbacks)]
    queries_to_try.append(random.choice(theme_group))
    queries_to_try.append("mystery cinematic dark")
    queries_to_try.append("suspense atmospheric slow")

    pexels_key = os.environ.get("PEXELS_API_KEY")
    if not pexels_key or pexels_key == "tu_clave_de_pexels_aqui":
        load_dotenv()
        pexels_key = os.environ.get("PEXELS_API_KEY")

    if not pexels_key or pexels_key == "tu_clave_de_pexels_aqui":
        raise RuntimeError(f"Error: PEXELS_API_KEY no está configurada y fal.ai falló.")

    headers = {"Authorization": pexels_key}
    history_videos_file = Path(__file__).parent / ".history_videos.json"
    used_video_ids = set()
    if history_videos_file.exists():
        try:
            with open(history_videos_file, "r", encoding="utf-8") as f:
                used_video_ids = set(json.load(f))
        except Exception:
            used_video_ids = set()
    
    for q_term in queries_to_try:
        if not q_term:
            continue
        try:
            # Buscar hasta 20 videos por página y rotar páginas aleatoriamente (1 a 3) para máxima variedad
            page_num = random.randint(1, 3)
            p_url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(q_term)}&orientation=portrait&per_page=20&page={page_num}"
            p_res = requests.get(p_url, headers=headers, timeout=12)
            if p_res.status_code == 200:
                videos = p_res.json().get("videos", [])
                # Filtrar videos que nunca se hayan usado antes
                fresh_videos = [v for v in videos if v.get("id") not in used_video_ids]
                candidate_pool = fresh_videos if fresh_videos else videos

                if candidate_pool:
                    # Selección aleatoria en lugar de índice fijo predecible
                    chosen_video = random.choice(candidate_pool)
                    v_id = chosen_video.get("id")
                    if v_id:
                        used_video_ids.add(v_id)
                        try:
                            with open(history_videos_file, "w", encoding="utf-8") as f:
                                json.dump(list(used_video_ids)[-100:], f)
                        except Exception:
                            pass

                    vfiles = chosen_video.get("video_files", [])
                    
                    # Priorizar 720x1280 (HD vertical veloz para móvil) o 1080x1920
                    target_file = next((f for f in vfiles if f.get("width") == 720 and f.get("height") == 1280), None)
                    if not target_file:
                        target_file = next((f for f in vfiles if f.get("width") == 1080 and f.get("height") == 1920), None)
                    if not target_file:
                        target_file = next((f for f in vfiles if (f.get("height", 0) or 0) > (f.get("width", 0) or 0)), None)
                    if not target_file and vfiles:
                        target_file = vfiles[0]
                    
                    if target_file and target_file.get("link"):
                        raw_stock = output_path + ".raw.mp4"
                        # Descarga robusta y rápida con curl en Termux
                        dl_cmd = [
                            "curl", "-s", "-L",
                            "-A", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                            "--max-time", "30",
                            "-o", raw_stock,
                            target_file["link"]
                        ]
                        subprocess.run(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                        
                        if os.path.exists(raw_stock) and os.path.getsize(raw_stock) > 10000:
                            cmd = [
                                "ffmpeg", "-y",
                                "-stream_loop", "-1", "-i", raw_stock,
                                "-t", str(duration_sec),
                                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                                "-r", "30",
                                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
                                output_path
                            ]
                            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                            if os.path.exists(raw_stock):
                                os.remove(raw_stock)
                            
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                                return f"Clip de stock video real 9:16 descargado de Pexels ({duration_sec}s continuos) en: {output_path}"
        except Exception:
            continue

    # Si tras las consultas específicas falla, usar query de rescate
    try:
        p_url = "https://api.pexels.com/videos/search?query=technology+cyber&orientation=portrait&per_page=10"
        p_res = requests.get(p_url, headers=headers, timeout=12)
        if p_res.status_code == 200:
            videos = p_res.json().get("videos", [])
            if videos:
                chosen_video = videos[scene_index % len(videos)]
                vfiles = chosen_video.get("video_files", [])
                target_file = next((f for f in vfiles if f.get("width") == 720 and f.get("height") == 1280), None)
                if not target_file:
                    target_file = vfiles[0] if vfiles else None
                if target_file and target_file.get("link"):
                    raw_stock = output_path + ".raw.mp4"
                    dl_cmd = [
                        "curl", "-s", "-L",
                        "-A", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                        "--max-time", "30",
                        "-o", raw_stock,
                        target_file["link"]
                    ]
                    subprocess.run(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    if os.path.exists(raw_stock) and os.path.getsize(raw_stock) > 10000:
                        cmd = [
                            "ffmpeg", "-y",
                            "-stream_loop", "-1", "-i", raw_stock,
                            "-t", str(duration_sec),
                            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                            "-r", "30",
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
                            output_path
                        ]
                        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                        if os.path.exists(raw_stock):
                            os.remove(raw_stock)
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                            return f"Clip de stock video real 9:16 descargado de Pexels ({duration_sec}s continuos) en: {output_path}"
    except Exception:
        pass

    if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
        return f"Clip de video 9:16 generado en: {output_path}"
    
    raise RuntimeError(f"No se pudo generar el clip de video para: {output_path}")


@mcp.tool()
def create_capcut_draft_project(
    project_name: str,
    video_paths: List[str],
    voiceover_path: str,
    music_path: str,
    custom_draft_dir: Optional[str] = None
) -> str:
    """
    Genera un borrador nativo de CapCut listo para abrir.
    - Canvas vertical 9:16 (1080x1920).
    - Clips de video organizados en secuencia en la pista de video.
    - Pista de voz de ElevenLabs al 100% de volumen (1.0).
    - Pista de música al 4% de volumen (0.04).
    """
    # Detección de la carpeta estándar de proyectos de CapCut
    if custom_draft_dir:
        draft_folder = os.path.join(custom_draft_dir, project_name)
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        draft_folder = os.path.join(
            local_app_data, "CapCut", "User Data", "Projects", "com.lveditor.draft", project_name
        )
    elif sys.platform == "darwin":
        draft_folder = os.path.expanduser(
            f"~/Movies/CapCut/User Data/Projects/com.lveditor.draft/{project_name}"
        )
    else:
        # En Android / Linux: verifica directorio accesible o fallback local
        android_capcut = "/sdcard/Movies/CapCut/User Data/Projects/com.lveditor.draft"
        if os.path.exists(android_capcut):
            draft_folder = os.path.join(android_capcut, project_name)
        else:
            draft_folder = os.path.abspath(f"./capcut_drafts/{project_name}")

    os.makedirs(draft_folder, exist_ok=True)

    # Duraciones
    video_durations = [get_media_duration_us(p) for p in video_paths]
    voice_duration = get_media_duration_us(voiceover_path)
    total_duration = max(sum(video_durations), voice_duration)

    videos_meta = []
    video_segments = []
    curr_time = 0

    for i, p in enumerate(video_paths):
        vid_id = str(uuid.uuid4())
        dur = video_durations[i]
        videos_meta.append({
            "id": vid_id,
            "path": os.path.abspath(p),
            "duration": dur,
            "type": "video",
            "width": 1080,
            "height": 1920
        })
        video_segments.append({
            "id": str(uuid.uuid4()),
            "material_id": vid_id,
            "target_timerange": {"duration": dur, "start": curr_time},
            "source_timerange": {"duration": dur, "start": 0},
            "volume": 0.0,  # 0% volumen para silenciar clips de video
            "speed": 1.0
        })
        curr_time += dur

    # Audio: Voz al 100%
    voice_id = str(uuid.uuid4())
    voice_meta = {
        "id": voice_id,
        "path": os.path.abspath(voiceover_path),
        "duration": voice_duration,
        "type": "audio"
    }
    voice_segment = {
        "id": str(uuid.uuid4()),
        "material_id": voice_id,
        "target_timerange": {"duration": voice_duration, "start": 0},
        "source_timerange": {"duration": voice_duration, "start": 0},
        "volume": 1.0,  # 100% de volumen para el diálogo de ElevenLabs
        "speed": 1.0
    }

    # Audio: Música al 15%
    music_duration = get_media_duration_us(music_path)
    music_id = str(uuid.uuid4())
    music_meta = {
        "id": music_id,
        "path": os.path.abspath(music_path),
        "duration": music_duration,
        "type": "audio"
    }
    music_segment = {
        "id": str(uuid.uuid4()),
        "material_id": music_id,
        "target_timerange": {"duration": total_duration, "start": 0},
        "source_timerange": {"duration": min(music_duration, total_duration), "start": 0},
        "volume": 0.09,  # 9% de volumen sutil para música de fondo
        "speed": 1.0
    }

    draft_content = {
        "canvas_config": {"width": 1080, "height": 1920, "ratio": "9:16"},
        "duration": total_duration,
        "materials": {
            "videos": videos_meta,
            "audios": [voice_meta, music_meta],
            "speeds": [],
            "transitions": []
        },
        "tracks": [
            {"id": str(uuid.uuid4()), "type": "video", "segments": video_segments},
            {"id": str(uuid.uuid4()), "type": "audio", "segments": [voice_segment]},
            {"id": str(uuid.uuid4()), "type": "audio", "segments": [music_segment]}
        ],
        "version": 2
    }

    create_time = int(time.time() * 1000)
    draft_meta_info = {
        "draft_id": str(uuid.uuid4()),
        "draft_name": project_name,
        "draft_root_path": os.path.abspath(draft_folder),
        "tm_draft_create": create_time,
        "tm_draft_modified": create_time,
        "draft_removable_storage_device": ""
    }

    with open(os.path.join(draft_folder, "draft_content.json"), "w", encoding="utf-8") as f:
        json.dump(draft_content, f, indent=2, ensure_ascii=False)

    with open(os.path.join(draft_folder, "draft_meta_info.json"), "w", encoding="utf-8") as f:
        json.dump(draft_meta_info, f, indent=2, ensure_ascii=False)

    return (
        f"Proyecto de CapCut generado en: {draft_folder}. "
        "Abre CapCut y verás el proyecto listo en tu lista de borradores."
    )


@mcp.tool()
def render_instant_video_ffmpeg(
    video_paths: List[str],
    voiceover_path: str,
    music_path: str,
    output_path: str
) -> str:
    """
    Renderiza directamente el video final con FFmpeg sin necesidad de abrir CapCut.
    Concatena los clips de video cuadro por cuadro (audio a 0%) y mezcla la voz al 100% con la música instrumental al 15%.
    Garantiza fluidez total a 30fps sin congelamientos visuales.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    inputs = []
    for vp in video_paths:
        inputs.extend(["-i", os.path.abspath(vp)])
    inputs.extend(["-i", os.path.abspath(voiceover_path)])
    inputs.extend(["-i", os.path.abspath(music_path)])

    num_videos = len(video_paths)
    v_concat_tags = "".join(f"[{i}:v]" for i in range(num_videos))
    voice_idx = num_videos
    music_idx = num_videos + 1

    filter_complex = (
        f"{v_concat_tags}concat=n={num_videos}:v=1:a=0[v_joined];"
        f"[v_joined]fps=30,format=yuv420p[outv];"
        f"[{voice_idx}:a]volume=1.0[v_voice];"
        f"[{music_idx}:a]volume=0.09[v_music];"
        f"[v_voice][v_music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-threads", "4",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return f"Video final exportado con éxito en: {output_path}"
    except subprocess.CalledProcessError as e:
        return f"Error renderizando con FFmpeg: {e.stderr.decode('utf-8', errors='ignore')}"


if __name__ == "__main__":
    mcp.run()


@mcp.tool()
def generate_video_clip_omni(
    prompt: str,
    output_path: str,
    duration_sec: int = 8,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Genera un clip de video usando Gemini Omni Flash (gemini-omni-1.1-flash) vía API Interactions.
    Aprovecha los tokens nativos de Google y devuelve el video en Base64.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key.startswith("tu_clave"):
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key or api_key.startswith("tu_clave"):
        return "Error: GEMINI_API_KEY no está configurada para Gemini Omni."

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={api_key}"
    payload = {
        "model": "gemini-omni-1.1-flash",
        "input": prompt,
        "response_format": {
            "type": "video",
            "aspect_ratio": aspect_ratio,
            "resolution": "720p"
        }
    }

    try:
        import base64
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
        if res.status_code == 200:
            data = res.json()
            video_b64 = None
            # Extraer del esquema interactions steps o output_video
            if "output_video" in data and isinstance(data["output_video"], dict):
                video_b64 = data["output_video"].get("data")
            elif "steps" in data:
                for step in data.get("steps", []):
                    if step.get("type") == "model_output":
                        for content in step.get("content", []):
                            if content.get("type") == "video" and "data" in content:
                                video_b64 = content["data"]
                                break

            if video_b64:
                raw_path = output_path + ".omni_raw.mp4"
                with open(raw_path, "wb") as f:
                    f.write(base64.b64decode(video_b64))

                if os.path.exists(raw_path) and os.path.getsize(raw_path) > 10000:
                    # Normalizar a 30fps fijos y duración
                    cmd = [
                        "ffmpeg", "-y",
                        "-stream_loop", "-1", "-i", raw_path,
                        "-t", str(duration_sec),
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                        "-r", "30",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
                        output_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    if os.path.exists(raw_path):
                        os.remove(raw_path)

                    if os.path.exists(output_path) and os.path.getsize(output_path) > 20000:
                        return f"✨ Clip generado con Gemini Omni Flash en: {output_path}"

            return f"No se encontró contenido de video en la respuesta de Omni Flash."
        elif res.status_code == 403:
            return f"Error de autenticación/clave filtrada en Gemini Omni (403): {res.text[:150]}"
        else:
            return f"Error en Gemini Omni Flash API ({res.status_code}): {res.text[:150]}"
    except Exception as e:
        return f"Error conectando con Gemini Omni Flash: {str(e)}"

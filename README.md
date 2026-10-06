# Servidor MCP: Pipeline de Automatización de Video

Pipeline de automatización de video basado en el protocolo **Model Context Protocol (MCP)** con soporte para:
1. **ElevenLabs TTS**: Generación de voz en off con recorte automático de silencios (`silenceremove`).
2. **Google AI Studio (Veo 2.0)**: Generación de clips de video en formato vertical 9:16.
3. **CapCut Drafts**: Generación de proyectos editables nativos de CapCut con pistas y volúmenes preconfigurados (Voz 100%, Música 7%).
4. **FFmpeg Direct Render**: Renderizado directo con optimización de consumo de CPU/temperatura para dispositivos móviles.

---

## 🚀 Requisitos e Instalación

### 1. Sistema
- **Python 3.10+**
- **FFmpeg & ffprobe**

En Termux (Android):
```bash
pkg install -y ffmpeg python
```

### 2. Dependencias de Python
```bash
pip install mcp requests google-genai
```

### 3. Variables de Entorno
Configura tus claves de API antes de iniciar:
```bash
export ELEVENLABS_API_KEY="tu_api_key_de_elevenlabs"
export GEMINI_API_KEY="tu_api_key_de_google_ai_studio"
```

---

## 🛠️ Herramientas MCP Disponibles

| Herramienta | Parámetros | Descripción |
| :--- | :--- | :--- |
| `generate_voiceover_elevenlabs` | `text`, `output_path`, `voice_id`, `model_id`, `trim_silence` | Genera locución con ElevenLabs y recorta pausas automáticamente con FFmpeg. |
| `generate_video_clip_veo` | `prompt`, `output_path`, `aspect_ratio` | Genera video 9:16 con Google Veo 2.0 (`veo-2.0-generate-001`). |
| `create_capcut_draft_project` | `project_name`, `video_paths`, `voiceover_path`, `music_path`, `custom_draft_dir` | Crea borrador editable de CapCut con volumen de voz al 100% y música al 7%. |
| `render_instant_video_ffmpeg` | `video_paths`, `voiceover_path`, `music_path`, `output_path` | Concatena y mezcla video y audio directamente con FFmpeg sin abrir CapCut. |

---

## 📱 Notas de Rendimiento en Android (Poco M8 5G)
- **ElevenLabs y Google Veo**: Se procesan en la nube (0% impacto térmico en el teléfono).
- **Generación de Borradores CapCut**: Generación instantánea de JSONs (0% impacto térmico).
- **CapCut App**: Se recomienda abrir el borrador generado directamente en la app de CapCut para exportar aprovechando la GPU y MediaCodec del teléfono.

---

## 🧪 Pruebas
Ejecuta el script de prueba para validar el funcionamiento:
```bash
python3 test_pipeline.py
```

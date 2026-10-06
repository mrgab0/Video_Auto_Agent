---
name: video-auto-agent
description: Pipeline agéntico de generación de videos verticales virales 9:16 para TikTok, Reels y Shorts. Genera guiones con Gemini, locución con ElevenLabs, clips de video con IA (Fal.ai Wan 2.1) o Pexels, y ensambla vía FFmpeg y CapCut.
---

# Video Auto Agent: Pipeline de Video Vertical

Esta habilidad permite al agente orquestar la creación completa de videos verticales hiperrealistas y de alto impacto.

## Cuándo activar esta Skill
- Cuando el usuario solicite crear o renderizar un video sobre un tema específico.
- Cuando se pida generar ideas virales, guiones estructurados para TikTok/Shorts/Reels o borradores de CapCut.

## Modos de Ejecución

### 1. Ejecución vía Grafo Autónomo (Recomendado)
Para generar un video completo de 40 a 55 segundos con ejecución paralela (fan-out) y resiliencia:
```bash
python3 pipeline_runner.py --topic "Tema del video"
```

### 2. Modos de Operación
- **Sin tema definido**: Selecciona automáticamente un tema misterioso o conspirativo no repetido:
  ```bash
  python3 pipeline_runner.py
  ```
- **Reanudar tras caída o desconexión**:
  ```bash
  python3 pipeline_runner.py --topic "Tema" --resume
  ```
- **Prueba sin consumo de tokens (Dry-run)**:
  ```bash
  python3 pipeline_runner.py --topic "Tema" --dry-run
  ```

## Estándares del Pipeline
1. **Duración estricta**: 40 a 55 segundos (110 a 130 palabras en español).
2. **Locución**: Voz 'Liam' (ElevenLabs) al 100% de volumen con recorte automático de silencios muertos.
3. **Escenas**: 5 a 6 escenas continuas de 8.0 segundos exactos en formato vertical 9:16.
4. **Música de fondo**: Instrumental ambiental calibrada al 15% de volumen.
5. **Salidas generadas**: Video MP4 final a 30fps CFR (1080x1920) + borrador editable de CapCut + `social_kit.json`.

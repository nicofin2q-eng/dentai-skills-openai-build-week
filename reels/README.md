# Editor de Reels por lotes (SEDDAMChile, Lundera)

Convierte videos verticales grabados con el celular en Reels listos para
Instagram, TikTok y YouTube Shorts: quita silencios, hace zoom alternado en
cada corte, normaliza el volumen, transcribe con Whisper y quema subtítulos con
el estilo de la marca.

## Uso

```bash
python reels/reel.py --brand seddamchile --out salida/ entrada/
python reels/reel.py --brand seddamchile video1.mp4 video2.mp4
python reels/reel.py --brand seddamchile --no-captions video.mp4   # sin subtítulos
```

Por cada video se generan en la carpeta de salida:

| Archivo | Contenido |
|---|---|
| `<nombre>_<marca>.mp4` | Reel final 1080×1920, 30 fps, H.264 + AAC, −14 LUFS |
| `<nombre>_<marca>.json` | Transcripción de Whisper con tiempos por palabra (para revisar) |
| `<nombre>_<marca>.ass` | Subtítulos con estilo; se pueden corregir a mano y volver a quemar |

## Pasos del proceso

1. **Silencios**: `silencedetect` de FFmpeg; se conservan los tramos con voz
   con un margen y un fundido corto en cada corte.
2. **Encuadre y zoom**: se lleva a 9:16 (1080×1920) y cada corte impar hace
   *punch-in* (zoom) centrado en la cara.
3. **Transcripción**: `faster-whisper` en CPU con una pista (`prompt`) que
   incluye el nombre de la marca para que lo escriba bien.
4. **Subtítulos**: frases de una línea; cada caja se mide con libass para que
   calce exacto con el texto. `replacements` corrige palabras que Whisper
   suele escribir mal.
5. **Exportación**: volumen normalizado en dos pasadas (EBU R128) y MP4 con
   `faststart`.

## Marcas

Cada marca es un archivo en `brands/`. Para agregar Lundera, copia
`brands/seddamchile.json` a `brands/lundera.json` y cambia colores, fuente,
`whisper.prompt` y `replacements`.

| Ajuste | Qué controla |
|---|---|
| `silence.threshold_db`, `min_duration_s`, `padding_s` | Qué cuenta como silencio y cuánto margen se deja |
| `zoom.punch_in`, `focus_y` | Cuánto zoom en cortes alternos y a qué altura se centra |
| `whisper.model`, `prompt` | Modelo (`small` rápido, `medium` más preciso) y vocabulario |
| `captions.*` | Fuente, tamaño, colores, caja y posición de los subtítulos |
| `audio.loudness_lufs` | Volumen final (−14 es el estándar de redes sociales) |

## Requisitos

- FFmpeg con libass y libx264.
- Python 3.10+ y `pip install -r reels/requirements.txt` (de preferencia en un
  entorno virtual).
- La primera vez Whisper descarga el modelo desde Hugging Face (`small` ≈ 480 MB).
  Si la descarga falla por el sistema Xet, usa `HF_HUB_DISABLE_XET=1`.
- La fuente de la marca debe estar instalada (SEDDAMChile usa *Inter Medium*).

## Grabación recomendada

Sube el video original de la cámara en lugar del exportado por CapCut (evita
comprimir dos veces). Si exportas desde CapCut: 1080p, 30 fps, sin HDR.

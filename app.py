import os
import uuid
import subprocess
import requests
import textwrap
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="AFTER Video Renderer")

class RenderRequest(BaseModel):
    video_url: str
    hook_text: str
    cta_text: str = "Entra a AFTER y liga en directo en la discoteca 🔥"
    duration: int = 11

def cleanup_files(*files):
    for f in files:
        if f and os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

@app.get("/")
def home():
    return {"status": "online", "service": "AFTER Video Renderer"}

@app.post("/render")
def render_video(data: RenderRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    input_video = f"/tmp/input_{job_id}.mp4"
    output_video = f"/tmp/output_{job_id}.mp4"

    # 1. Descargar vídeo de Pexels
    try:
        r = requests.get(data.video_url, timeout=40, stream=True)
        r.raise_for_status()
        with open(input_video, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error descargando vídeo: {str(e)}")

    # 2. Formatear texto
    wrapped_hook = "\n".join(textwrap.wrap(data.hook_text, width=30))
    clean_hook = wrapped_hook.replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")
    clean_cta = data.cta_text.replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")

    # 3. Filtro FFmpeg a 1080x1920 nativo con bordes negros sólidos y audio silencioso
    filter_complex = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"drawtext=text='{clean_hook}':fontcolor=white:fontsize=52:borderw=5:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.16:line_spacing=15,"
        f"drawtext=text='{clean_cta}':fontcolor=0x00FFA3:fontsize=42:borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.82[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-t", str(data.duration),
        "-i", input_video,
        "-f", "lavfi", "-t", str(data.duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        output_video
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cleanup_files(input_video, output_video)
        raise HTTPException(status_code=500, detail=f"Error FFmpeg: {result.stderr[-200:]}")

    background_tasks.add_task(cleanup_files, input_video, output_video)

    return FileResponse(
        output_video,
        media_type="video/mp4",
        filename="video_after_1080p.mp4"
    )

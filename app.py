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
    cta_text: str = "Entra a AFTER y liga en directo en la discoteca"
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

    # 1. Descargar vídeo original de Pexels
    try:
        r = requests.get(data.video_url, timeout=40, stream=True)
        r.raise_for_status()
        with open(input_video, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error descargando vídeo: {str(e)}")

    # 2. Formatear y envolver texto (escapado seguro para drawtext)
    wrapped_hook = "\n".join(textwrap.wrap(data.hook_text, width=28))
    clean_hook = (
        wrapped_hook.replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )
    clean_cta = (
        data.cta_text.replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )

    # 3. Filtro FFmpeg optimizado a 720x1280 vertical
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    
    filter_complex = (
        f"[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
        f"drawtext=fontfile='{font_path}':text='{clean_hook}':fontcolor=white:fontsize=36:borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.16:line_spacing=12,"
        f"drawtext=fontfile='{font_path}':text='{clean_cta}':fontcolor=0x00FFA3:fontsize=28:borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.82[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-t", str(data.duration),
        "-i", input_video,
        "-f", "lavfi", "-t", str(data.duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-crf", "26",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "96k",
        output_video
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cleanup_files(input_video, output_video)
        raise HTTPException(status_code=500, detail=f"FFmpeg falló: {result.stderr[-300:]}")

    background_tasks.add_task(cleanup_files, input_video, output_video)

    return FileResponse(
        output_video,
        media_type="video/mp4",
        filename="video_after_720p.mp4"
    )

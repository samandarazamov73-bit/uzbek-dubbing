import os
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager

# ===========================
# DIRS
# ===========================
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ===========================
# JOB STORAGE (in-memory)
# ===========================
jobs: dict = {}

# ===========================
# APP
# ===========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 UzDub API ishga tushdi!")
    print("📦 AI modellari yuklanmoqda...")
    yield
    print("👋 Server to'xtatildi")

app = FastAPI(
    title="UzDub API",
    description="English → Uzbek AI Video Dubbing",
    version="1.0.0",
    lifespan=lifespan
)

# ===========================
# CORS — Netlify + HuggingFace uchun
# ===========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================
# STATIC FILES
# ===========================
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/static", StaticFiles(directory="frontend"), name="frontend")

# ===========================
# ROUTES
# ===========================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Frontend saitni ko'rsatish"""
    index_path = Path("frontend/index.html")
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>🎬 UzDub API ishlayapti!</h1><p>Version: 1.0.0</p>")

@app.get("/health")
async def health():
    return {"status": "ok", "message": "UzDub API ishlayapti!"}

@app.get("/api/info")
async def info():
    return {
        "name": "UzDub",
        "version": "1.0.0",
        "description": "English → Uzbek AI Video Dubbing",
        "features": ["whisper", "translation", "tts", "lipsync"]
    }

# ===========================
# DUB ENDPOINT
# ===========================
@app.post("/dub")
async def start_dubbing(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    source_lang: str = Form(default="en"),
    target_lang: str = Form(default="uz"),
    lip_sync: bool = Form(default=True),
):
    """Video yuklash va dublyaj ishini boshlash"""

    # Fayl tekshirish
    allowed_types = [
        "video/mp4", "video/quicktime",
        "video/x-msvideo", "video/x-matroska", "video/webm"
    ]
    if video.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Faqat video fayllar qabul qilinadi (MP4, MOV, AVI, MKV, WEBM)"
        )

    # Hajm tekshirish (500MB)
    max_size = 500 * 1024 * 1024
    content = await video.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="Fayl hajmi 500MB dan oshmasligi kerak"
        )

    # Job ID yaratish
    job_id = str(uuid.uuid4())

    # Faylni saqlash
    ext = Path(video.filename).suffix or ".mp4"
    input_path = UPLOAD_DIR / f"{job_id}{ext}"
    with open(input_path, "wb") as f:
        f.write(content)

    # Job boshlang'ich holati
    jobs[job_id] = {
        "status": "processing",
        "step": "transcribing",
        "progress": 10,
        "result_url": None,
        "error": None,
    }

    # Background da ishlatish
    background_tasks.add_task(
        run_dubbing_pipeline,
        job_id=job_id,
        input_path=str(input_path),
        source_lang=source_lang,
        target_lang=target_lang,
        lip_sync=lip_sync,
    )

    return {"job_id": job_id, "message": "Dublyaj boshlandi"}

# ===========================
# STATUS ENDPOINT
# ===========================
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Job holatini tekshirish"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job topilmadi")
    return jobs[job_id]

# ===========================
# DELETE ENDPOINT
# ===========================
@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Job va fayllarni o'chirish"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job topilmadi")

    for f in UPLOAD_DIR.glob(f"{job_id}*"):
        f.unlink(missing_ok=True)
    for f in OUTPUT_DIR.glob(f"{job_id}*"):
        f.unlink(missing_ok=True)

    del jobs[job_id]
    return {"message": "O'chirildi"}

# ===========================
# BACKGROUND TASK
# ===========================
async def run_dubbing_pipeline(
    job_id: str,
    input_path: str,
    source_lang: str,
    target_lang: str,
    lip_sync: bool,
):
    """AI dublyaj pipeline ni background da ishlatish"""
    from backend.dubbing import DubbingPipeline

    pipeline = DubbingPipeline(job_id=job_id, jobs=jobs)

    try:
        output_path = OUTPUT_DIR / f"{job_id}_dubbed.mp4"

        await pipeline.run(
            input_path=input_path,
            output_path=str(output_path),
            source_lang=source_lang,
            target_lang=target_lang,
            lip_sync=lip_sync,
        )

        jobs[job_id].update({
            "status": "done",
            "step": "done",
            "progress": 100,
            "result_url": f"/outputs/{job_id}_dubbed.mp4",
        })

    except Exception as e:
        print(f"❌ Job {job_id} xatosi: {e}")
        jobs[job_id].update({
            "status": "error",
            "step": "error",
            "error": str(e),
        })

    finally:
        try:
            Path(input_path).unlink(missing_ok=True)
        except Exception:
            pass

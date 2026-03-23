import os
import asyncio
import logging
from typing import Optional
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

from youtube_downloader import download_video
from s3_uploader import S3Uploader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("downloader.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("youtube_downloader")

app = FastAPI(title="YouDescribe Youtube-Downloader", version="2.0.0")

DOWNLOAD_DIR = os.path.expanduser(os.getenv("DOWNLOAD_DIR", "~/Downloads/YouDescribeDownloadedVideos"))
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "youdescribe-downloaded-youtube-videos")
AWS_REGION = os.getenv("AWS_REGION", "us-west-1")
PORT = int(os.getenv("PORT", "8001"))

s3_uploader = S3Uploader(bucket_name=S3_BUCKET_NAME, region=AWS_REGION)

download_jobs: dict = {}


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadRequest(BaseModel):
    youtube_id: str


class DownloadStatusResponse(BaseModel):
    youtube_id: str
    status: DownloadStatus
    s3_paths: Optional[dict] = None
    error: Optional[str] = None


async def download_and_upload(youtube_id: str):
    try:
        download_jobs[youtube_id] = {"status": DownloadStatus.DOWNLOADING, "s3_paths": None, "error": None}

        logger.info(f"[{youtube_id}] Starting download...")
        success = await asyncio.to_thread(download_video, youtube_id, DOWNLOAD_DIR)

        if not success:
            download_jobs[youtube_id]["status"] = DownloadStatus.FAILED
            download_jobs[youtube_id]["error"] = "Download failed after all attempts"
            logger.error(f"[{youtube_id}] Download failed")
            return

        download_jobs[youtube_id]["status"] = DownloadStatus.UPLOADING
        logger.info(f"[{youtube_id}] Uploading to S3...")
        video_dir = os.path.join(DOWNLOAD_DIR, youtube_id)
        s3_paths = await asyncio.to_thread(s3_uploader.upload_video_package, youtube_id, video_dir)

        if not s3_paths.get("video"):
            download_jobs[youtube_id]["status"] = DownloadStatus.FAILED
            download_jobs[youtube_id]["error"] = "S3 upload failed for video file"
            logger.error(f"[{youtube_id}] S3 upload failed")
            return

        download_jobs[youtube_id]["status"] = DownloadStatus.COMPLETED
        download_jobs[youtube_id]["s3_paths"] = s3_paths
        logger.info(f"[{youtube_id}] Upload complete. S3 paths: {s3_paths}")

    except Exception as e:
        logger.error(f"[{youtube_id}] Unexpected error: {e}", exc_info=True)
        download_jobs[youtube_id] = {
            "status": DownloadStatus.FAILED,
            "s3_paths": None,
            "error": str(e),
        }


@app.post("/api/download", response_model=DownloadStatusResponse)
async def trigger_download(data: DownloadRequest, background_tasks: BackgroundTasks):
    youtube_id = data.youtube_id

    if youtube_id in download_jobs:
        current_status = download_jobs[youtube_id]["status"]
        if current_status in (DownloadStatus.DOWNLOADING, DownloadStatus.UPLOADING, DownloadStatus.PENDING):
            logger.info(f"[{youtube_id}] Already in progress (status: {current_status})")
            return DownloadStatusResponse(youtube_id=youtube_id, status=current_status)

    try:
        if s3_uploader.check_video_exists(youtube_id):
            logger.info(f"[{youtube_id}] Already exists in S3, skipping download")
            s3_prefix = f"videos/{youtube_id}"
            s3_paths = {
                "video": f"{s3_prefix}/{youtube_id}.mp4",
                "metadata": f"{s3_prefix}/{youtube_id}.json",
            }
            download_jobs[youtube_id] = {
                "status": DownloadStatus.COMPLETED,
                "s3_paths": s3_paths,
                "error": None,
            }
            return DownloadStatusResponse(
                youtube_id=youtube_id,
                status=DownloadStatus.COMPLETED,
                s3_paths=s3_paths,
            )
    except Exception as e:
        logger.warning(f"[{youtube_id}] Could not check S3 existence: {e}")

    download_jobs[youtube_id] = {"status": DownloadStatus.PENDING, "s3_paths": None, "error": None}
    background_tasks.add_task(download_and_upload, youtube_id)

    logger.info(f"[{youtube_id}] Download queued")
    return DownloadStatusResponse(youtube_id=youtube_id, status=DownloadStatus.PENDING)


@app.get("/api/download/status/{youtube_id}", response_model=DownloadStatusResponse)
async def get_download_status(youtube_id: str):
    if youtube_id not in download_jobs:
        raise HTTPException(status_code=404, detail=f"No download job found for {youtube_id}")

    job = download_jobs[youtube_id]
    return DownloadStatusResponse(
        youtube_id=youtube_id,
        status=job["status"],
        s3_paths=job.get("s3_paths"),
        error=job.get("error"),
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "YouDescribe Youtube-Downloader",
        "download_dir": DOWNLOAD_DIR,
        "s3_bucket": S3_BUCKET_NAME,
        "active_jobs": len([j for j in download_jobs.values() if j["status"] in ("pending", "downloading", "uploading")]),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Youtube-Downloader on port {PORT}")
    logger.info(f"Download directory: {DOWNLOAD_DIR}")
    logger.info(f"S3 bucket: {S3_BUCKET_NAME}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

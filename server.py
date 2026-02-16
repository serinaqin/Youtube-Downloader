"""
Youtube-Downloader Service
FastAPI server that downloads YouTube videos using a residential IP,
uploads them to AWS S3, and notifies the YouDescribeX API backend.

Endpoints:
    POST /api/download          - Trigger a video download
    GET  /api/download/status   - Check download status
    GET  /health                - Health check
"""

import os
import asyncio
import logging
from typing import Optional
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

from youtube_downloader import download_video
from s3_uploader import S3Uploader

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("downloader.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("youtube_downloader")

app = FastAPI(title="YouDescribe Youtube-Downloader", version="1.0.0")

# Configuration from environment
DOWNLOAD_DIR = os.path.expanduser(os.getenv("DOWNLOAD_DIR", "~/Downloads/YouDescribeDownloadedVideos"))
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "youdescribe-downloaded-youtube-videos")
AWS_REGION = os.getenv("AWS_REGION", "us-west-1")
API_CALLBACK_URL = os.getenv("API_CALLBACK_URL", "http://localhost:4001")
PORT = int(os.getenv("PORT", "8001"))

# S3 uploader instance
s3_uploader = S3Uploader(bucket_name=S3_BUCKET_NAME, region=AWS_REGION)

# In-memory job tracking
download_jobs: dict = {}


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadRequest(BaseModel):
    youtube_id: str
    user_id: Optional[str] = None
    ai_user_id: Optional[str] = None
    callback_url: Optional[str] = None  # Override for the callback URL


class DownloadStatusResponse(BaseModel):
    youtube_id: str
    status: DownloadStatus
    s3_paths: Optional[dict] = None
    error: Optional[str] = None


async def download_and_upload(youtube_id: str, user_id: Optional[str], ai_user_id: Optional[str], callback_url: str):
    """Background task: download video, upload to S3, notify API."""
    try:
        # Update status
        download_jobs[youtube_id] = {"status": DownloadStatus.DOWNLOADING, "s3_paths": None, "error": None}

        # Step 1: Download the video locally
        logger.info(f"[{youtube_id}] Starting download...")
        success = await asyncio.to_thread(download_video, youtube_id, DOWNLOAD_DIR)

        if not success:
            download_jobs[youtube_id]["status"] = DownloadStatus.FAILED
            download_jobs[youtube_id]["error"] = "Download failed after all attempts"
            logger.error(f"[{youtube_id}] Download failed")
            # Notify API of failure
            try:
                requests.post(
                    f"{callback_url}/api/users/pipeline-failure",
                    json={"youtube_id": youtube_id, "error": "Video download failed", "stage": "download"},
                    timeout=10,
                )
            except Exception:
                pass
            return

        # Step 2: Upload to S3
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

        # Step 3: Notify the API that download + upload is complete
        callback_payload = {
            "youtube_id": youtube_id,
            "user_id": user_id,
            "ai_user_id": ai_user_id,
            "s3_paths": s3_paths,
            "s3_bucket": S3_BUCKET_NAME,
            "status": "completed",
        }

        logger.info(f"[{youtube_id}] Notifying API at {callback_url}/api/users/download-complete")
        try:
            response = requests.post(
                f"{callback_url}/api/users/download-complete",
                json=callback_payload,
                timeout=30,
            )
            logger.info(f"[{youtube_id}] API callback response: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[{youtube_id}] API callback failed: {e}")
            # The download/upload still succeeded, just the callback failed
            # The API can poll /api/download/status to recover

    except Exception as e:
        logger.error(f"[{youtube_id}] Unexpected error: {e}", exc_info=True)
        download_jobs[youtube_id] = {
            "status": DownloadStatus.FAILED,
            "s3_paths": None,
            "error": str(e),
        }


@app.post("/api/download", response_model=DownloadStatusResponse)
async def trigger_download(data: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Trigger a YouTube video download.
    The download runs in the background. Use /api/download/status to check progress.
    """
    youtube_id = data.youtube_id
    callback_url = data.callback_url or API_CALLBACK_URL

    # Check if video is already being processed
    if youtube_id in download_jobs:
        current_status = download_jobs[youtube_id]["status"]
        if current_status in (DownloadStatus.DOWNLOADING, DownloadStatus.UPLOADING, DownloadStatus.PENDING):
            logger.info(f"[{youtube_id}] Already in progress (status: {current_status})")
            return DownloadStatusResponse(
                youtube_id=youtube_id,
                status=current_status,
            )

    # Check if already in S3
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

            # Still notify the API so it can proceed
            background_tasks.add_task(
                _notify_api_existing,
                youtube_id, data.user_id, data.ai_user_id, s3_paths, callback_url,
            )

            return DownloadStatusResponse(
                youtube_id=youtube_id,
                status=DownloadStatus.COMPLETED,
                s3_paths=s3_paths,
            )
    except Exception as e:
        logger.warning(f"[{youtube_id}] Could not check S3 existence: {e}")

    # Start the download in the background
    download_jobs[youtube_id] = {"status": DownloadStatus.PENDING, "s3_paths": None, "error": None}
    background_tasks.add_task(download_and_upload, youtube_id, data.user_id, data.ai_user_id, callback_url)

    logger.info(f"[{youtube_id}] Download queued")
    return DownloadStatusResponse(
        youtube_id=youtube_id,
        status=DownloadStatus.PENDING,
    )


async def _notify_api_existing(youtube_id: str, user_id: str, ai_user_id: str, s3_paths: dict, callback_url: str):
    """Notify the API about an already-existing S3 video."""
    try:
        requests.post(
            f"{callback_url}/api/users/download-complete",
            json={
                "youtube_id": youtube_id,
                "user_id": user_id,
                "ai_user_id": ai_user_id,
                "s3_paths": s3_paths,
                "s3_bucket": S3_BUCKET_NAME,
                "status": "completed",
            },
            timeout=30,
        )
    except Exception as e:
        logger.error(f"[{youtube_id}] API notification for existing video failed: {e}")


@app.get("/api/download/status/{youtube_id}", response_model=DownloadStatusResponse)
async def get_download_status(youtube_id: str):
    """Check the status of a video download job."""
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
    """Health check endpoint."""
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
    logger.info(f"API callback URL: {API_CALLBACK_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

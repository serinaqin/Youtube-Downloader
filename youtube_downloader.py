"""
YouTube Downloader Module
Downloads YouTube videos, metadata, captions, and thumbnails.
Extracted from the AI-generated-AD pipeline for local execution with residential IP.
"""

import os
import json
import subprocess
import re
import logging
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import timedelta

logger = logging.getLogger("youtube_downloader")


def get_video_metadata(video_id: str) -> dict:
    """Fetch video metadata using yt-dlp: title, description, duration, category."""
    url = f"https://www.youtube.com/watch?v={video_id}"

    title_cmd = ["yt-dlp", "--get-title", url]
    desc_cmd = ["yt-dlp", "--get-description", url]
    duration_cmd = ["yt-dlp", "--get-duration", url]
    category_cmd = ["yt-dlp", "--print", "categories", url]

    title = "Unknown Title"
    description = ""
    video_length = 0
    category = "Unknown Category"

    # Get title
    try:
        result = subprocess.run(title_cmd, capture_output=True, text=True, check=True, timeout=60)
        if result.stdout.strip():
            title = result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error fetching title: {e}")

    # Get description
    try:
        result = subprocess.run(desc_cmd, capture_output=True, text=True, check=True, timeout=60)
        if result.stdout.strip():
            description = result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error fetching description: {e}")

    # Get category
    try:
        result = subprocess.run(category_cmd, capture_output=True, text=True, check=True, timeout=60)
        if result.stdout.strip():
            category_str = result.stdout.strip()
            if category_str.startswith("['") and category_str.endswith("']"):
                category = category_str[2:-2]
            else:
                category = category_str
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error fetching category: {e}")
        try:
            info_json_cmd = ["yt-dlp", "--dump-json", url]
            result = subprocess.run(info_json_cmd, capture_output=True, text=True, check=True, timeout=120)
            if result.stdout.strip():
                video_info = json.loads(result.stdout)
                if "categories" in video_info and video_info["categories"]:
                    category = video_info["categories"][0]
        except Exception as e2:
            logger.error(f"Alternative category fetch failed: {e2}")

    # Get duration
    try:
        result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True, timeout=60)
        duration_str = result.stdout.strip()

        if duration_str.isdigit():
            video_length = int(duration_str)
        elif re.match(r"^\d+:\d+:\d+$", duration_str) or re.match(r"^\d+:\d+$", duration_str):
            parts = [int(p) for p in duration_str.split(":")]
            if len(parts) == 3:
                video_length = int(timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2]).total_seconds())
            elif len(parts) == 2:
                video_length = int(timedelta(minutes=parts[0], seconds=parts[1]).total_seconds())
        else:
            logger.warning(f"Invalid duration format: {duration_str}")
            info_cmd = ["yt-dlp", "--print", "duration", url]
            try:
                result = subprocess.run(info_cmd, capture_output=True, text=True, check=True, timeout=60)
                if result.stdout.strip().isdigit():
                    video_length = int(result.stdout.strip())
            except subprocess.CalledProcessError:
                logger.error("Could not determine video duration")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Error fetching duration: {e}")

    return {
        "title": title,
        "description": description,
        "video_length": video_length,
        "category": category,
    }


def download_video(video_id: str, output_dir: str) -> bool:
    """
    Download a YouTube video, its metadata, captions, and thumbnail.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save downloaded files

    Returns:
        True if download succeeded, False otherwise
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    # Create the output directory
    video_dir = os.path.join(output_dir, video_id)
    Path(video_dir).mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    video_path = os.path.join(video_dir, f"{video_id}.mp4")
    metadata_path = os.path.join(video_dir, f"{video_id}.json")
    if os.path.exists(video_path) and os.path.exists(metadata_path):
        file_size = os.path.getsize(video_path)
        if file_size > 0:
            logger.info(f"Video {video_id} already downloaded ({file_size / (1024*1024):.2f} MB). Skipping.")
            return True

    # Fetch metadata
    logger.info(f"Fetching metadata for {video_id}...")
    metadata = get_video_metadata(video_id)
    logger.info(f"Title: {metadata['title']}, Duration: {metadata['video_length']}s, Category: {metadata['category']}")

    # Prepare metadata + captions JSON
    captions_data = {
        "title": metadata["title"],
        "description": metadata["description"],
        "video_length": metadata["video_length"],
        "category": metadata["category"],
        "captions": [],
    }

    # Download captions (youtube-transcript-api v1.x API)
    try:
        ytt_api = YouTubeTranscriptApi()
        fetched_transcript = ytt_api.fetch(video_id)
        captions_data["captions"] = fetched_transcript.to_raw_data()
        logger.info("Captions downloaded successfully.")
    except Exception as e:
        logger.warning(f"Captions not available: {e}")

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(captions_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Metadata saved to: {metadata_path}")

    # Download thumbnail
    thumbnail_path = os.path.join(video_dir, f"{video_id}_thumbnail.jpg")
    logger.info("Downloading thumbnail...")
    thumbnail_cmd = [
        "yt-dlp",
        "--write-thumbnail",
        "--skip-download",
        "--convert-thumbnails", "jpg",
        "-o", os.path.join(video_dir, video_id),
        url,
    ]

    try:
        subprocess.run(thumbnail_cmd, check=True, capture_output=True, timeout=60)
        possible_thumbnails = [
            os.path.join(video_dir, f"{video_id}.jpg"),
            os.path.join(video_dir, f"{video_id}.webp"),
        ]
        for thumb in possible_thumbnails:
            if os.path.exists(thumb):
                if thumb != thumbnail_path:
                    os.rename(thumb, thumbnail_path)
                logger.info(f"Thumbnail saved to: {thumbnail_path}")
                break
    except Exception as e:
        logger.warning(f"Thumbnail download failed: {e}")

    # Download video
    logger.info(f"Downloading video {video_id}...")
    download_commands = [
        # Primary method
        [
            "yt-dlp",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--hls-prefer-native",
            "--ignore-errors",
            "-o", video_path,
            url,
        ],
        # Fallback method
        [
            "yt-dlp",
            "--format-sort", "res,codec",
            "--merge-output-format", "mp4",
            "--allow-unplayable-formats",
            "--ignore-errors",
            "--no-playlist",
            "-o", video_path,
            url,
        ],
        # Last resort
        [
            "yt-dlp",
            "--no-check-formats",
            "--ignore-errors",
            "--no-playlist",
            "-o", video_path,
            url,
        ],
    ]

    for i, cmd in enumerate(download_commands):
        try:
            logger.info(f"Download attempt {i + 1}/{len(download_commands)}...")
            subprocess.run(cmd, check=True, timeout=600)
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                file_size = os.path.getsize(video_path) / (1024 * 1024)
                logger.info(f"Download successful! File size: {file_size:.2f} MB")
                return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Download attempt {i + 1} failed: {e}")
            continue

    logger.error(f"All download attempts failed for video {video_id}")
    return False


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Download YouTube video by ID")
    parser.add_argument("video_id", help="YouTube video ID (e.g. dQw4w9WgXcQ)")
    parser.add_argument("--output-dir", default="./downloads", help="Output directory")
    args = parser.parse_args()

    success = download_video(args.video_id, args.output_dir)
    if success:
        print("Download completed successfully.")
    else:
        print("Download failed.")

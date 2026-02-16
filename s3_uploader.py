"""
S3 Uploader Module
Handles uploading downloaded video files and metadata to AWS S3.
"""

import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("youtube_downloader")


class S3Uploader:
    def __init__(self, bucket_name: str, region: str = "us-west-1"):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )

    def upload_file(self, local_path: str, s3_key: str, content_type: str = None) -> bool:
        """Upload a single file to S3."""
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            logger.info(f"Uploading {local_path} -> s3://{self.bucket_name}/{s3_key}")
            self.s3_client.upload_file(local_path, self.bucket_name, s3_key, ExtraArgs=extra_args)
            logger.info(f"Successfully uploaded to s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {local_path} to S3: {e}")
            return False
        except FileNotFoundError:
            logger.error(f"File not found: {local_path}")
            return False

    def upload_video_package(self, video_id: str, video_dir: str) -> dict:
        """
        Upload all files for a video to S3.
        Returns a dict of S3 paths for each uploaded file.
        """
        s3_paths = {}
        s3_prefix = f"videos/{video_id}"

        # Upload the video file (.mp4)
        video_path = os.path.join(video_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            s3_key = f"{s3_prefix}/{video_id}.mp4"
            if self.upload_file(video_path, s3_key, content_type="video/mp4"):
                s3_paths["video"] = s3_key
        else:
            logger.warning(f"Video file not found: {video_path}")

        # Upload the metadata JSON
        metadata_path = os.path.join(video_dir, f"{video_id}.json")
        if os.path.exists(metadata_path):
            s3_key = f"{s3_prefix}/{video_id}.json"
            if self.upload_file(metadata_path, s3_key, content_type="application/json"):
                s3_paths["metadata"] = s3_key
        else:
            logger.warning(f"Metadata file not found: {metadata_path}")

        # Upload the thumbnail if it exists
        thumbnail_path = os.path.join(video_dir, f"{video_id}_thumbnail.jpg")
        if os.path.exists(thumbnail_path):
            s3_key = f"{s3_prefix}/{video_id}_thumbnail.jpg"
            if self.upload_file(thumbnail_path, s3_key, content_type="image/jpeg"):
                s3_paths["thumbnail"] = s3_key

        return s3_paths

    def check_video_exists(self, video_id: str) -> bool:
        """Check if a video already exists in S3."""
        try:
            s3_key = f"videos/{video_id}/{video_id}.mp4"
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False

    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading from S3."""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None

# YouDescribe Youtube-Downloader

Local YouTube video downloader service for the YouDescribeX platform. Runs on a machine with a **residential IP** to avoid YouTube IP blocking on AWS.

## Architecture Role

This service is **Part A** of the YouDescribeX AI pipeline split:

```
[User Request] → [YouDescribeX-API] → [Youtube-Downloader (LOCAL)]
                                              ↓
                                        Download Video
                                              ↓
                                        Upload to S3
                                              ↓
                                     [YouDescribeX-API] → [AI-generated-AD (AWS EC2)]
                                                                ↓
                                                          Fetch from S3
                                                          Run AI Pipeline
                                                                ↓
                                                          Return Results
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Make sure `yt-dlp` is installed:
```bash
pip install yt-dlp
# or
brew install yt-dlp
```

3. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

4. Run the server:
```bash
python server.py
```

The server starts on port **8001** by default.

## API Endpoints

### POST /api/download
Trigger a video download. Runs in the background.

```json
{
  "youtube_id": "BB49x_uMlGA",
  "user_id": "optional_user_id",
  "ai_user_id": "optional_ai_user_id"
}
```

### GET /api/download/status/{youtube_id}
Check download status.

### GET /health
Service health check.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - |
| `AWS_REGION` | AWS region | `us-west-1` |
| `S3_BUCKET_NAME` | S3 bucket for videos | `youdescribe-downloaded-youtube-videos` |
| `DOWNLOAD_DIR` | Local download directory | `~/Downloads/YouDescribeDownloadedVideos` |
| `API_CALLBACK_URL` | YouDescribeX API URL | `http://localhost:4001` |
| `PORT` | Server port | `8001` |

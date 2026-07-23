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
| `SNS_TOPIC_ARN` | SNS topic for failure email alerts (empty = disabled) | - |
| `NOTIFY_COOLDOWN_SECONDS` | Min seconds between alert emails | `1800` |

## Failure Email Alerts (AWS SNS)

When a download or S3 upload fails, the server publishes an alert to an SNS
topic; email subscribers get notified. A global cooldown (default 30 min)
prevents email storms during mass failures — suppressed failures are counted
and reported in the next alert. If `SNS_TOPIC_ARN` is not set, alerting is
silently disabled and the service behaves exactly as before.

### One-time AWS setup (admin)

```bash
# 1. Create the topic (note the TopicArn in the output)
aws sns create-topic --name youtube-downloader-alerts \
    --region us-west-1 --profile youdescribe

# 2. Subscribe each recipient (they must click the confirmation email)
aws sns subscribe --topic-arn <TOPIC_ARN> --protocol email \
    --notification-endpoint you@example.com \
    --region us-west-1 --profile youdescribe

# 3. Allow the downloader's IAM user to publish to this topic only
aws iam put-user-policy --user-name <DOWNLOADER_IAM_USER> \
    --policy-name sns-publish-downloader-alerts \
    --policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Action": "sns:Publish",
        "Resource": "<TOPIC_ARN>"
      }]
    }' --profile youdescribe
```

### Enable on the machine running the server

Add to `.env`:

```
SNS_TOPIC_ARN=<TOPIC_ARN>
NOTIFY_COOLDOWN_SECONDS=1800
```

Restart the server. Verify with a video ID that is guaranteed to fail
(e.g. a deleted video): `curl -X POST localhost:8001/api/download -H
'Content-Type: application/json' -d '{"youtube_id": "xxxxxxxxxxx"}'` and
check that the alert email arrives with the yt-dlp error tail.

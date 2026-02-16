#!/bin/bash
# Setup script for YouDescribe Youtube-Downloader AWS resources
# Run this after configuring AWS CLI with your zhenzhen-youdescribe-2 credentials:
#   aws configure --profile youdescribe
# Then run: AWS_PROFILE=youdescribe bash setup_aws.sh

set -e

BUCKET_NAME="youdescribe-videos"
REGION="us-west-2"

echo "=== YouDescribe AWS Setup ==="
echo "Account:"
aws sts get-caller-identity

echo ""
echo "--- Step 1: Create S3 Bucket ---"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    echo "Bucket '$BUCKET_NAME' already exists."
else
    echo "Creating bucket '$BUCKET_NAME' in $REGION..."
    aws s3api create-bucket \
        --bucket "$BUCKET_NAME" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
    echo "Bucket created."
fi

echo ""
echo "--- Step 2: Enable versioning ---"
aws s3api put-bucket-versioning \
    --bucket "$BUCKET_NAME" \
    --versioning-configuration Status=Enabled
echo "Versioning enabled."

echo ""
echo "--- Step 3: Set lifecycle policy (clean up old videos after 30 days) ---"
aws s3api put-bucket-lifecycle-configuration \
    --bucket "$BUCKET_NAME" \
    --lifecycle-configuration '{
        "Rules": [
            {
                "ID": "CleanupOldVideos",
                "Filter": {"Prefix": "videos/"},
                "Status": "Enabled",
                "Expiration": {"Days": 30},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 7}
            }
        ]
    }'
echo "Lifecycle policy set (videos expire after 30 days)."

echo ""
echo "--- Step 4: Block public access ---"
aws s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
echo "Public access blocked."

echo ""
echo "=== Setup Complete ==="
echo "Bucket: s3://$BUCKET_NAME"
echo "Region: $REGION"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and fill in your AWS credentials"
echo "2. Run: python server.py"

# Cloud Storage Integration

This document explains how to configure and use cloud storage backends for email archives.

## Overview

The Email Intelligence POC supports multiple storage backends:
- **Local Filesystem** - Traditional file paths
- **AWS S3** - Amazon S3 buckets
- **Google Drive** - Google Drive files (with OAuth2 frontend integration)
- Azure Blob Storage (coming soon)

## Supported URI Formats

### Local Files
```
/path/to/file.mbox
file:///path/to/file.mbox
```

### AWS S3
```
s3://bucket-name/path/to/file.mbox
```

### Google Drive
```
gdrive://1abc234def567890  (File ID)
https://drive.google.com/file/d/1abc234def567890/view
```

**Note**: Google Drive integration has been upgraded to industry-standard OAuth2 flow.  
See **[GOOGLE_DRIVE_INTEGRATION.md](./GOOGLE_DRIVE_INTEGRATION.md)** for complete setup instructions.

## Configuration

### 1. AWS S3 Setup

**Install dependencies:**
```bash
pip install boto3
```

**Configure credentials** (choose one):

Option A - Environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

Option B - AWS credentials file (`~/.aws/credentials`):
```ini
[default]
aws_access_key_id = your_access_key
aws_secret_access_key = your_secret_key
region = us-east-1
```

Option C - IAM Role (for EC2/ECS/Lambda):
No configuration needed - uses instance metadata

**Usage in mailbox configuration:**
```json
{
  "name": "S3 Archive",
  "mailbox_type": "mbox",
  "connection_config": {
    "file_path": "s3://my-email-bucket/archives/2023/emails.mbox"
  }
}
```

### 2. Google Drive Setup

The platform now supports two methods for Google Drive integration:

#### Method A: Frontend OAuth2 Integration (Recommended)

**Features:**
- User-friendly authentication via Google account
- Interactive file browser with search
- No service account needed
- Direct user authorization

**Setup:**

1. **Google Cloud Console Configuration:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create or select a project
   - Enable Google Drive API
   - Create OAuth2 credentials (Web application)
   - Add authorized JavaScript origins: `http://localhost:3000`
   - Add redirect URIs: `http://localhost:3000/auth/google/callback`

2. **Environment Configuration (.env):**
```bash
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

3. **Usage:**
   - In mailbox creation, select "Google Drive" as file source
   - Click "Select from Google Drive"
   - Authenticate with Google account
   - Browse and select files

#### Method B: Service Account (Backend Processing)

**For automated/batch processing:**

```bash
pip install google-auth google-auth-httplib2 google-api-python-client
```

1. Create Service Account in Google Cloud Console
2. Download JSON key file
3. Share files with service account email
4. Configure:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

**Get File ID from Google Drive URL:**
```
https://drive.google.com/file/d/1abc234def567890/view
                              ^^^^^^^^^^^^^^^^^ This is the File ID
```

**Usage in mailbox configuration:**

Frontend OAuth2 method:
```json
{
  "name": "Google Drive Archive",
  "mailbox_type": "mbox",
  "connection_config": {
    "file_source": "google_drive",
    "google_drive_file_id": "1abc234def567890",
    "google_drive_file_name": "archive.mbox"
  }
}
```

Service account method:
```json
{
  "name": "Google Drive Archive",
  "mailbox_type": "mbox",
  "connection_config": {
    "file_path": "gdrive://1abc234def567890"
  }
}
```

## Database Schema

The `mailboxes` table stores the file location in `connection_config`:

```sql
CREATE TABLE mailboxes (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    mailbox_type TEXT NOT NULL,  -- 'mbox', 'pst', 'olm', etc.
    connection_config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

Example record:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Company Archive 2023",
  "mailbox_type": "mbox",
  "connection_config": {
    "file_path": "s3://company-emails/archives/2023-q4.mbox"
  },
  "is_active": true
}
```

## API Usage

### Create Mailbox with Cloud Storage

```bash
curl -X POST http://localhost:8000/api/mailboxes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "S3 Archive",
    "mailbox_type": "mbox",
    "connection_config": {
      "file_path": "s3://my-bucket/emails/archive.mbox"
    }
  }'
```

### Start Processing Job

```bash
curl -X POST http://localhost:8000/api/mailboxes/{mailbox_id}/process \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "extraction",
    "total_records": 1000,
    "batch_size": 100
  }'
```

The system will automatically:
1. Detect the storage backend from the URI
2. Download the file if needed (S3/Google Drive)
3. Process the emails
4. Clean up temporary files when done

## Security Best Practices

### AWS S3
- Use IAM roles instead of access keys when possible
- Apply least-privilege principle (read-only access)
- Enable S3 bucket encryption
- Use VPC endpoints for private network access
- Enable CloudTrail logging

### Google Drive
- Use service accounts, not user accounts
- Grant minimal permissions (Viewer only)
- Rotate service account keys regularly
- Monitor API usage quotas
- Use domain-wide delegation for G Suite

### General
- Never commit credentials to Git
- Use environment variables or secure vaults (AWS Secrets Manager, etc.)
- Encrypt data at rest and in transit
- Implement access logging and auditing
- Use temporary credentials when possible

## Troubleshooting

### S3 Access Denied
```
Failed to download from S3: An error occurred (AccessDenied)
```
**Solutions:**
- Verify IAM permissions include `s3:GetObject`
- Check bucket policy allows access
- Ensure correct AWS region
- Verify credentials are configured

### Google Drive: Permission Denied
```
Failed to download from Google Drive: <HttpError 403>
```
**Solutions for OAuth2 method:**
- Ensure user has access to the file
- Check OAuth scopes include drive.readonly
- Verify access token is not expired
- Re-authenticate if necessary

**Solutions for Service Account method:**
- Verify service account has access to the file
- Check if file is in a Shared Drive (requires additional setup)
- Ensure Google Drive API is enabled in Google Cloud Console
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct

### File Not Found
```
File not found: gdrive://file_id
```
**Solutions:**
- Verify file ID is correct
- Check if file was deleted or moved
- Ensure service account still has access
- Try using the full Google Drive URL instead

## Performance Considerations

### Large Files
- Files are downloaded to `/tmp` (or OS temp directory)
- Ensure sufficient disk space for large archives
- Consider processing files in batches
- Use cloud processing (EC2, Cloud Functions) near storage

### Network Transfer
- S3 same-region transfers are faster and free
- Google Drive has daily API quotas
- Consider using VPCs for private network access
- Monitor bandwidth costs

### Caching
- Downloaded files are not cached between sessions
- Implement custom caching if processing same file repeatedly
- Consider keeping processed metadata in database

## Migration from Local Paths

To migrate existing mailboxes from local paths to cloud storage:

1. **Upload files to cloud storage**
2. **Update database records:**

```sql
-- Update S3 path
UPDATE mailboxes
SET connection_config = jsonb_set(
    connection_config,
    '{file_path}',
    '"s3://my-bucket/archives/file.mbox"'
)
WHERE id = 'mailbox-uuid';

-- Update Google Drive path
UPDATE mailboxes
SET connection_config = jsonb_set(
    connection_config,
    '{file_path}',
    '"gdrive://file_id"'
)
WHERE id = 'mailbox-uuid';
```

3. **Test connection** using the test endpoint:
```bash
curl -X POST http://localhost:8000/api/mailboxes/{mailbox_id}/test-connection
```

## Example: Complete Setup

### S3 Example

1. Create S3 bucket and upload file:
```bash
aws s3 mb s3://company-email-archives
aws s3 cp /local/archive.mbox s3://company-email-archives/2023/archive.mbox
```

2. Create IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::company-email-archives/*"]
    }
  ]
}
```

3. Configure application:
```bash
export AWS_ACCESS_KEY_ID=AKIAxxxxxxxx
export AWS_SECRET_ACCESS_KEY=xxxxxxxx
```

4. Create mailbox via API (see API Usage section above)

### Google Drive Example

1. Create service account and download JSON key
2. Share Drive file with service account email
3. Configure application:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/app/keys/service-account.json
```
4. Get file ID from Drive URL
5. Create mailbox via API with `gdrive://` URI

## Support

For issues or questions:
- Check logs in `backend/logs/backend.log`
- Enable debug logging: `logging.getLogger('src.storage').setLevel(logging.DEBUG)`
- Review cloud provider documentation
- Check IAM/service account permissions

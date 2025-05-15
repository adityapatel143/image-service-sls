# Serverless Image Upload Service

This service provides a scalable solution for uploading, storing, and retrieving images using AWS serverless technology. It is designed to support multiple users concurrently and provides a robust API for image management.

## Features

- **Image Upload:** Support for both multipart/form-data and JSON (base64 encoded) upload methods
- **Metadata Storage:** Automatic storage of image metadata in DynamoDB
- **Advanced Image Search:** Multiple filtering options including user, tags, filename, date range, and more
- **Pagination & Sorting:** Support for result pagination and customizable sorting for efficient browsing
- **Scalability:** Built with AWS Lambda for automatic scaling to handle multiple concurrent users
- **Image Processing:** Background processing of uploaded images via S3 event triggers
- **Comprehensive API:** Endpoints for uploading, retrieving, updating, and deleting images
- **Access Control:** Support for public/private visibility settings

## Project Structure

```
docker-compose.yml       # Docker configuration for LocalStack
localstack-endpoints.json # LocalStack endpoint configuration
package.json             # Node.js package configuration
README.md                # This file
requirements.txt         # Python dependencies
serverless.yml           # Serverless Framework configuration
app/
  image_handler.py       # Image processing logic
  image_schema.py        # Data validation schemas
  s3_handler.py          # S3 interaction logic
```

## Architecture

The service is built using the following AWS services:

- **AWS Lambda:** For serverless API handlers and image processing
- **Amazon S3:** For scalable image storage
- **Amazon DynamoDB:** For storing image metadata
- **Amazon API Gateway:** For HTTP API endpoints

## API Endpoints

### Image Management

- `POST /images/upload` - Upload a new image with metadata
- `GET /images` - List images with advanced filtering options
- `GET /images/{id}` - Get a single image's metadata
- `GET /images/{id}/download` - Download an image by ID with various output options
- `PUT /images/{id}` - Update image metadata
- `DELETE /images/{id}` - Delete an image and its metadata


## Image Download

The `/images/{id}/download` endpoint allows downloading images by their ID using different methods:

### Query Parameters

- `type` (optional) - The download method to use. Available options:
  - `redirect` (default) - Generates a pre-signed URL and redirects to it
  - `binary` - Returns the image as binary data in the response
  - `base64` - Returns the image as a base64-encoded string in a JSON response

### Examples

- Direct download with browser redirect: `GET /images/{id}/download`
- Download as binary for programmatic access: `GET /images/{id}/download?type=binary`
- Get base64-encoded data: `GET /images/{id}/download?type=base64`

## Image Listing with Filtering

The image listing API (`GET /images`) supports multiple filtering options to help you find exactly the images you need:

| Parameter  | Description                                           | Example                  |
|------------|-------------------------------------------------------|--------------------------|
| userId     | Filter by user ID                                     | `?userId=user123`        |
| tag        | Filter by tag                                         | `?tag=vacation`          |
| visibility | Filter by visibility level (public, private, friends) | `?visibility=public`     |
| filename   | Filter by partial filename match                      | `?filename=vacation`     |
| dateFrom   | Filter by upload date (from)                          | `?dateFrom=2023-01-01`   |
| dateTo     | Filter by upload date (to)                            | `?dateTo=2023-12-31`     |
| sort       | Sort by field (createdAt, filename)                   | `?sort=filename`         |
| order      | Sort order (asc, desc)                                | `?order=asc`             |
| limit      | Limit results (max: 100)                              | `?limit=20`              |

### Example Queries:

```
# Basic query - get public images
GET /images

# Get images from a specific user
GET /images?userId=user123

# Search for beach photos uploaded in summer 2023
GET /images?filename=beach&dateFrom=2023-06-01&dateTo=2023-09-01

# Get the most recently uploaded vacation photos
GET /images?tag=vacation&sort=createdAt&order=desc&limit=10

# Combined filtering with pagination
GET /images?userId=user123&visibility=public&limit=5&nextToken=eyJpZC4uLn0=
```

## Image Upload Formats

### Multipart/form-data

```
POST /images/upload
Content-Type: multipart/form-data

file: [binary data]
userId: user123
description: My vacation photo
visibility: public
tags: ["vacation", "beach", "summer"]
```

### JSON with Base64 Encoded Image

```json
POST /images/upload
Content-Type: application/json

{
  "image": {
    "filename": "vacation.jpg",
    "content": "base64EncodedImageData",
    "contentType": "image/jpeg"
  },
  "metadata": {
    "userId": "user123",
    "description": "My vacation photo",
    "visibility": "public",
    "tags": ["vacation", "beach", "summer"]
  }
}
```

## Development Setup

### Prerequisites

- [Node.js](https://nodejs.org/) (for Serverless Framework)
- [Python](https://www.python.org/) (3.8 or higher)
- [Docker](https://www.docker.com/) (for local dependencies)
- [LocalStack](https://localstack.cloud/) (for local AWS emulation)

### Local Development

1. Create a Python virtual environment:

```bash
python -m venv .venv
```

2. Activate the Python Environment (Windows):

```bash
source .venv/Scripts/activate
```

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize Node.js project and install Serverless Framework:

```bash
npm init --y
npm install -g serverless@3
npm install -D serverless-localstack serverless-python-requirements
```

5. Start LocalStack:

```bash
docker compose up -d
```

6. Deploy to LocalStack:

```bash
serverless deploy --stage local
```

### Production Deployment

```bash
serverless deploy --stage prod
```

## Configuration

The service can be configured through the `serverless.yml` file:

- **S3 Bucket:** Name and configuration for image storage
- **DynamoDB Tables:** Tables for storing metadata
- **Lambda Functions:** API handlers and event processors
- **IAM Permissions:** Access control for AWS resources

## Scaling Considerations

- DynamoDB is configured with on-demand capacity for automatic scaling
- Lambda functions automatically scale to handle concurrent requests
- S3 provides virtually unlimited storage for images
- Consider using CloudFront for caching frequently accessed images

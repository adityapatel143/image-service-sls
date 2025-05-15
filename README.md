# Serverless Image Upload Service

This service provides a scalable solution for uploading, storing, and retrieving images using AWS serverless technology. It is designed to support multiple users concurrently and provides a robust API for image management.

## Features

- **Image Upload:** Support for both multipart/form-data and JSON (base64 encoded) upload methods
- **Metadata Storage:** Automatic storage of image metadata in DynamoDB
- **Scalability:** Built with AWS Lambda for automatic scaling to handle multiple concurrent users
- **Image Processing:** Background processing of uploaded images via S3 event triggers
- **Comprehensive API:** Endpoints for uploading, retrieving, updating, and deleting images
- **Access Control:** Support for public/private visibility settings

## Architecture

The service is built using the following AWS services:

- **AWS Lambda:** For serverless API handlers and image processing
- **Amazon S3:** For scalable image storage
- **Amazon DynamoDB:** For storing image metadata
- **Amazon API Gateway:** For HTTP API endpoints

## API Endpoints

### Image Management

- `POST /images/upload` - Upload a new image with metadata
- `GET /images` - List images (with optional filtering by user or tags)
- `GET /images/{id}` - Get a single image's metadata
- `PUT /images/{id}` - Update image metadata
- `DELETE /images/{id}` - Delete an image and its metadata

### General API

- `POST /items` - Create a new item
- `GET /items` - List all items
- `GET /items/{id}` - Get a single item
- `PUT /items/{id}` - Update an item
- `DELETE /items/{id}` - Delete an item
- `POST /upload` - Legacy file upload endpoint

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
- [Docker](https://www.docker.com/) (for local dependencies)
- [LocalStack](https://localstack.cloud/) (for local AWS emulation)

### Local Development

1. Install dependencies:

```bash
npm install
pip install -r requirements.txt
```

2. Start LocalStack:

```bash
docker-compose up -d
```

3. Deploy to LocalStack:

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

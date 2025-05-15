import os
import json
import base64
import logging
import uuid
import boto3
import re
from io import BytesIO
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def upload_file_handler(event, context):
    """
    HTTP handler for uploading files to S3 bucket
    
    Expected request format:
    - Content-Type: multipart/form-data OR application/json
    - For application/json: Body contains base64 encoded file and filename
    
    Args:
        event: HTTP event
        context: Lambda context
    
    Returns:
        HTTP response with upload result
    """
    try:
        logger.info('Received file upload request')
        
        # Extract the S3 bucket name from environment variables
        bucket_name = os.environ['S3_BUCKET']
        
        # Check content type to determine how to handle the request
        content_type = event.get('headers', {}).get('Content-Type', '') or event.get('headers', {}).get('content-type', '')
        
        if 'application/json' in content_type:
            # Handle JSON request with base64 encoded file
            return handle_json_upload(event, bucket_name)
        elif 'multipart/form-data' in content_type:
            # Handle multipart form-data request (standard file upload)
            return handle_multipart_upload(event, bucket_name)
        else:
            # Return error for unsupported content types
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Unsupported Content-Type. Use application/json with base64 encoded file or multipart/form-data'
                })
            }
            
    except Exception as e:
        logger.error(f'Error processing file upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def handle_multipart_upload(event, bucket_name):
    """
    Handle file upload from multipart/form-data request
    
    Expected format:
    - HTTP POST with Content-Type: multipart/form-data
    - Form field 'file' containing the file data
    
    Args:
        event: HTTP event with multipart/form-data body
        bucket_name: S3 bucket name
        
    Returns:
        HTTP response with upload result
    """
    try:
        # Get the content type header with boundary
        content_type = event.get('headers', {}).get('Content-Type', '') or event.get('headers', {}).get('content-type', '')
        
        # Extract the body content
        body = event.get('body', '')
        
        # If body is base64 encoded, decode it first
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body)
        else:
            body = body.encode('utf-8') if isinstance(body, str) else body
            
        # Parse the multipart form data using custom parser
        # Since we can't rely on cgi anymore, we'll implement a simpler parser
        files, file_name = parse_multipart_body(body, content_type)
        
        if not files or file_name is None:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'No file found in the form data'})
            }
        
        file_content = files
        filename = file_name
        
        # Generate a unique object key to avoid overwriting existing files
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_extension = os.path.splitext(filename)[1]
        file_name_without_ext = os.path.splitext(filename)[0]
        unique_id = str(uuid.uuid4())[:8]
        
        object_key = f"{file_name_without_ext}_{timestamp}_{unique_id}{file_extension}"
        
        # Get the appropriate endpoint for LocalStack if in local environment
        endpoint_url = None
        stage = os.environ.get('STAGE', 'dev')
        if stage == 'local':
            endpoint_url = 'http://localhost:4566'  # Default LocalStack endpoint
        
        # Upload the file to S3
        s3_client = boto3.client('s3', endpoint_url=endpoint_url)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=file_content
        )
        
        logger.info(f"File uploaded successfully to {bucket_name}/{object_key} via multipart/form-data")
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'File uploaded successfully',
                'filename': filename,
                'object_key': object_key,
                'bucket': bucket_name,
                'size': len(file_content)
            })
        }
            
    except Exception as e:
        logger.error(f'Error in multipart file upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def parse_multipart_body(body, content_type):
    """
    Simple parser for multipart/form-data requests
    
    Args:
        body: The raw body content
        content_type: Content-Type header with boundary
        
    Returns:
        Tuple of (file_content, filename) or (None, None) if parsing failed
    """
    try:
        # Extract boundary
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            logger.error("Could not find boundary in content type")
            return None, None
            
        boundary = boundary_match.group(1)
        
        # Make sure body is bytes
        if isinstance(body, str):
            body = body.encode('utf-8')
            
        # Split the body by boundary
        boundary_bytes = f'--{boundary}'.encode('utf-8')
        parts = body.split(boundary_bytes)
        
        # Skip the first empty part and the last boundary marker
        parts = parts[1:-1]
        
        for part in parts:
            # Split headers and content
            try:
                headers_end = part.find(b'\r\n\r\n')
                if headers_end == -1:
                    continue
                    
                headers_raw = part[:headers_end].strip()
                content = part[headers_end + 4:].strip()  # +4 for the double CRLF
                
                # If this part has the Content-Disposition header with filename
                if b'Content-Disposition: form-data; name="file"' in headers_raw:
                    # Extract filename
                    filename_match = re.search(rb'filename="([^"]+)"', headers_raw)
                    if filename_match:
                        filename = filename_match.group(1).decode('utf-8')
                        # Remove end boundary marker if present
                        if content.endswith(b'--\r\n'):
                            content = content[:-4]
                        elif content.endswith(b'\r\n'):
                            content = content[:-2]
                            
                        return content, filename
            except Exception as e:
                logger.error(f"Error parsing part: {str(e)}")
                continue
                
        logger.error("No file found in multipart data")
        return None, None
        
    except Exception as e:
        logger.error(f"Error parsing multipart body: {str(e)}")
        return None, None

def handle_json_upload(event, bucket_name):
    """
    Handle file upload from JSON request with base64 encoded file
    
    Expected JSON format:
    {
        "filename": "example.txt",
        "content": "base64EncodedFileContent"
    }
    
    Args:
        event: HTTP event with JSON body
        bucket_name: S3 bucket name
        
    Returns:
        HTTP response with upload result
    """
    try:
        # Parse request body
        body = json.loads(event['body'])
        
        # Extract filename and file content
        filename = body.get('filename')
        file_content_b64 = body.get('content')
        
        if not filename or not file_content_b64:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Missing required fields: filename and content'
                })
            }
        
        # Generate a unique object key to avoid overwriting existing files
        # Format: original_filename_timestamp_uuid.extension
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_extension = os.path.splitext(filename)[1]
        file_name_without_ext = os.path.splitext(filename)[0]
        unique_id = str(uuid.uuid4())[:8]
        
        object_key = f"{file_name_without_ext}_{timestamp}_{unique_id}{file_extension}"
        
        # Decode the base64 content
        try:
            file_content = base64.b64decode(file_content_b64)
        except Exception as e:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': f'Invalid base64 encoded content: {str(e)}'
                })
            }
        
        # Get the appropriate endpoint for LocalStack if in local environment
        endpoint_url = None
        stage = os.environ.get('STAGE', 'dev')
        if stage == 'local':
            endpoint_url = 'http://localhost:4566'  # Default LocalStack endpoint
        
        # Upload the file to S3
        s3_client = boto3.client('s3', endpoint_url=endpoint_url)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=file_content
        )
        
        logger.info(f"File uploaded successfully to {bucket_name}/{object_key}")
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'File uploaded successfully',
                'filename': filename,
                'object_key': object_key,
                'bucket': bucket_name,
                'size': len(file_content)
            })
        }
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        logger.error(f'Error in JSON file upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

import json
import logging
import os
import uuid
import re
import boto3
from urllib.parse import unquote_plus
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_dynamodb_client():
    """Initialize DynamoDB client with proper configuration"""
    stage = os.environ.get('STAGE', 'dev')
    endpoint_url = None
    if stage == 'local':
        endpoint_url = 'http://localhost:4566'  # Default LocalStack endpoint
    
    return boto3.resource('dynamodb', endpoint_url=endpoint_url)

def get_s3_client():
    """Initialize S3 client with proper configuration"""
    stage = os.environ.get('STAGE', 'dev')
    endpoint_url = None
    if stage == 'local':
        endpoint_url = 'http://localhost:4566'  # Default LocalStack endpoint
    
    return boto3.client('s3', endpoint_url=endpoint_url)

def is_image_file(filename):
    """
    Check if a filename corresponds to an image file based on its extension
    
    Args:
        filename: The file name to check
        
    Returns:
        True if it's an image file, False otherwise
    """
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff']
    file_ext = os.path.splitext(filename.lower())[1]
    return file_ext in image_extensions

def find_image_metadata(object_key, bucket_name):
    """
    Find image metadata in DynamoDB by object key and bucket name
    
    Args:
        object_key: S3 object key
        bucket_name: S3 bucket name
        
    Returns:
        Image metadata if found, None otherwise
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ.get('IMAGES_TABLE')
        if not table_name:
            logger.warning("IMAGES_TABLE environment variable not set")
            return None
            
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Query for the image by objectKey
        response = table.scan(
            FilterExpression="objectKey = :objectKey AND bucket = :bucket",
            ExpressionAttributeValues={
                ":objectKey": object_key,
                ":bucket": bucket_name
            }
        )
        
        items = response.get('Items', [])
        return items[0] if items else None
        
    except Exception as e:
        logger.error(f"Error finding image metadata: {str(e)}")
        return None

def create_image_metadata_entry(object_key, bucket_name, content_type, size):
    """
    Create a basic metadata entry for an image uploaded directly to S3
    
    Args:
        object_key: S3 object key
        bucket_name: S3 bucket name
        content_type: Content type of the file
        size: File size in bytes
        
    Returns:
        The created metadata
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ.get('IMAGES_TABLE')
        if not table_name:
            logger.error("IMAGES_TABLE environment variable not set")
            raise ValueError("IMAGES_TABLE environment variable not set")
            
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Generate ID and timestamps
        image_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        # Extract filename from object key
        # Object keys may have a format like "original_20240515_123045_abcd1234.jpg"
        # Try to extract the original filename
        filename = object_key
        # See if it matches our naming pattern
        pattern = r"(.+)_\d{8}_\d{6}_[a-f0-9]{8}(\.[a-zA-Z0-9]+)$"
        match = re.match(pattern, object_key)
        if match:
            filename = match.group(1) + match.group(2)
        
        # Create metadata item
        item = {
            'id': image_id,
            'objectKey': object_key,
            'bucket': bucket_name,
            'filename': filename,
            'contentType': content_type,
            'size': size,
            'userId': 'system',  # Default user for automatically created entries
            'visibility': 'private',  # Default to private for auto-created entries
            'description': '',
            'tags': [],
            'createdAt': timestamp,
            'updatedAt': timestamp,
            'autoCreated': True  # Flag to indicate this was auto-created
        }
        
        # Store metadata in DynamoDB
        table.put_item(Item=item)
        logger.info(f"Created metadata for {object_key}")
        
        return item
        
    except Exception as e:
        logger.error(f"Error creating image metadata: {str(e)}")
        raise

def process_image(bucket_name, object_key):
    """
    Process an image file
    This function can be enhanced to generate thumbnails, extract EXIF data, etc.
    
    Args:
        bucket_name: S3 bucket name
        object_key: S3 object key
    """
    logger.info(f"Processing image {object_key} from bucket {bucket_name}")
    
    # Here we would add code to process the image
    # - Generate thumbnails
    # - Extract EXIF data
    # - Run image recognition
    # - etc.
    
    # For now, we'll just log that we processed the image
    logger.info(f"Image processing completed for {object_key}")

def process_s3_event(event, context):
    """
    Lambda function that processes S3 events when images are uploaded
    
    Args:
        event: The S3 event
        context: Lambda context
    
    Returns:
        Response with information about the processed images
    """
    try:
        # Log the event for debugging
        logger.info('Received S3 event: %s', json.dumps(event))
        
        # Extract S3 bucket and object details from the event
        s3_records = event.get('Records', [])
        
        if not s3_records:
            logger.warning('No S3 records found in the event')
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No S3 records in event'})
            }
        
        # Process each record
        processed_images = []
        for record in s3_records:
            if record.get('eventSource') == 'aws:s3' and record.get('eventName', '').startswith('ObjectCreated:'):
                bucket_name = record['s3']['bucket']['name']
                object_key = unquote_plus(record['s3']['object']['key'])
                object_size = record['s3']['object']['size']
                
                # Check if this object is already in our metadata table
                image_metadata = find_image_metadata(object_key, bucket_name)
                
                if not image_metadata:
                    logger.info(f"Processing new image: {object_key}")
                    # This image was uploaded directly to S3, not through our API
                    # Let's create a metadata entry for it
                    try:
                        # Get the file's content type from S3
                        s3_client = get_s3_client()
                        object_info = s3_client.head_object(
                            Bucket=bucket_name,
                            Key=object_key
                        )
                        content_type = object_info.get('ContentType', 'application/octet-stream')
                        
                        # Create basic metadata entry
                        create_image_metadata_entry(
                            object_key=object_key,
                            bucket_name=bucket_name,
                            content_type=content_type,
                            size=object_size
                        )
                    except Exception as e:
                        logger.error(f"Error creating metadata for {object_key}: {str(e)}")
                
                # Process the image if it's an image file
                if is_image_file(object_key):
                    try:
                        process_image(bucket_name, object_key)
                    except Exception as e:
                        logger.error(f"Error processing image {object_key}: {str(e)}")
                
                processed_images.append({
                    'objectKey': object_key,
                    'bucket': bucket_name,
                    'size': object_size,
                    'eventTime': record.get('eventTime')
                })
                
                # Log the file upload information
                logger.info('Image processed: %s from bucket %s, size: %s bytes', 
                           object_key, bucket_name, object_size)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {len(processed_images)} image upload events',
                'images': processed_images
            })
        }
        
    except Exception as e:
        logger.error('Error processing S3 event: %s', str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

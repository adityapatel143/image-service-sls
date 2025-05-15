import os
import json
import base64
import logging
import uuid
import boto3
import re
import decimal
from io import BytesIO
from datetime import datetime
from jsonschema import validate, ValidationError
from .image_schema import IMAGE_METADATA_SCHEMA

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Helper class to convert Decimal to float for JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj) if obj % 1 else int(obj)
        # Let the base class default method handle other types
        return super(DecimalEncoder, self).default(obj)

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

def upload_image_handler(event, context):
    """
    HTTP handler for uploading images to S3 bucket with metadata stored in DynamoDB
    
    Expected request format:
    - Content-Type: multipart/form-data OR application/json
    - For application/json: Body contains base64 encoded file, filename, and metadata
    
    Args:
        event: HTTP event
        context: Lambda context
    
    Returns:
        HTTP response with upload result
    """
    try:
        logger.info('Received image upload request')
        
        # Extract bucket and table names from environment variables
        bucket_name = os.environ['S3_BUCKET']
        table_name = os.environ['IMAGES_TABLE']
        
        # Check content type to determine how to handle the request
        content_type = event.get('headers', {}).get('Content-Type', '') or event.get('headers', {}).get('content-type', '')
        
        if 'application/json' in content_type:
            # Handle JSON request with base64 encoded file
            return handle_json_image_upload(event, bucket_name, table_name)
        elif 'multipart/form-data' in content_type:
            # Handle multipart form-data request (standard file upload)
            return handle_multipart_image_upload(event, bucket_name, table_name)
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
        logger.error(f'Error processing image upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def handle_multipart_image_upload(event, bucket_name, table_name):
    """
    Handle image upload from multipart/form-data request with metadata
    
    Expected format:
    - HTTP POST with Content-Type: multipart/form-data
    - Form field 'file' containing the file data
    - Form fields for metadata (userId, description, tags, etc.)
    
    Args:
        event: HTTP event with multipart/form-data body
        bucket_name: S3 bucket name
        table_name: DynamoDB table name
        
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
            
        # Parse the multipart form data
        form_data = parse_multipart_form(body, content_type)
        
        if not form_data or 'file' not in form_data or not form_data['file'].get('content'):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'No file found in the form data'})
            }
        
        # Extract file content and metadata from form data
        file_content = form_data['file'].get('content')
        filename = form_data['file'].get('filename')
        content_type = form_data['file'].get('content_type', '')
        
        # Extract metadata from form fields
        metadata = {
            'filename': filename,
            'contentType': content_type,
            'userId': form_data.get('userId', {}).get('content', ''),
            'description': form_data.get('description', {}).get('content', ''),
            'visibility': form_data.get('visibility', {}).get('content', 'public')
        }
        
        # Extract tags if available
        if 'tags' in form_data and form_data['tags'].get('content'):
            try:
                tags_str = form_data['tags'].get('content')
                if isinstance(tags_str, bytes):
                    tags_str = tags_str.decode('utf-8')
                metadata['tags'] = json.loads(tags_str)
            except:
                # If tags parsing fails, try splitting by comma
                if isinstance(tags_str, bytes):
                    tags_str = tags_str.decode('utf-8')
                metadata['tags'] = [tag.strip() for tag in tags_str.split(',')]
        
        # Validate metadata against schema
        try:
            validate(instance=metadata, schema=IMAGE_METADATA_SCHEMA)
        except ValidationError as e:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': f'Invalid metadata: {str(e)}'
                })
            }
            
        # Upload image and store metadata
        return upload_image_with_metadata(file_content, metadata, bucket_name, table_name)
            
    except Exception as e:
        logger.error(f'Error in multipart image upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def handle_json_image_upload(event, bucket_name, table_name):
    """
    Handle image upload from JSON request with base64 encoded file and metadata
    
    Expected JSON format:
    {
        "image": {
            "filename": "example.jpg",
            "content": "base64EncodedFileContent",
            "contentType": "image/jpeg"
        },
        "metadata": {
            "userId": "user123",
            "description": "My vacation photo",
            "visibility": "public",
            "tags": ["vacation", "beach", "summer"]
        }
    }
    
    Args:
        event: HTTP event with JSON body
        bucket_name: S3 bucket name
        table_name: DynamoDB table name
        
    Returns:
        HTTP response with upload result
    """
    try:
        # Parse request body
        body = json.loads(event['body'])
        
        # Extract image data and metadata
        image_data = body.get('image', {})
        metadata = body.get('metadata', {})
        
        # Validate required fields
        if not image_data:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Missing image data'
                })
            }
            
        filename = image_data.get('filename')
        file_content_b64 = image_data.get('content')
        content_type = image_data.get('contentType', '')
        
        if not filename or not file_content_b64:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Missing required fields in image data: filename and content'
                })
            }
            
        # Combine image data and metadata
        complete_metadata = {
            'filename': filename,
            'contentType': content_type,
            'userId': metadata.get('userId', ''),
            'description': metadata.get('description', ''),
            'visibility': metadata.get('visibility', 'public'),
            'tags': metadata.get('tags', [])
        }
        
        # Validate metadata against schema
        try:
            validate(instance=complete_metadata, schema=IMAGE_METADATA_SCHEMA)
        except ValidationError as e:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': f'Invalid metadata: {str(e)}'
                })
            }
            
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
            
        # Upload image and store metadata
        return upload_image_with_metadata(file_content, complete_metadata, bucket_name, table_name)
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        logger.error(f'Error in JSON image upload: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def upload_image_with_metadata(file_content, metadata, bucket_name, table_name):
    """
    Upload image to S3 and store metadata in DynamoDB
    
    Args:
        file_content: Binary content of the image file
        metadata: Dictionary containing image metadata
        bucket_name: S3 bucket name
        table_name: DynamoDB table name
        
    Returns:
        HTTP response with upload result
    """
    # Generate unique ID for the image
    image_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    # Generate a unique object key
    file_extension = os.path.splitext(metadata['filename'])[1]
    file_name_without_ext = os.path.splitext(metadata['filename'])[0]
    object_key = f"{file_name_without_ext}_{timestamp.replace(':', '-').replace('.', '-')}_{image_id[:8]}{file_extension}"
    
    try:
        # Upload the file to S3
        s3_client = get_s3_client()
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=file_content,
            ContentType=metadata.get('contentType', 'application/octet-stream')
        )
        
        # Create metadata record for DynamoDB
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Prepare item for DynamoDB
        item = {
            'id': image_id,
            'objectKey': object_key,
            'bucket': bucket_name,
            'userId': metadata['userId'],
            'filename': metadata['filename'],
            'contentType': metadata['contentType'],
            'description': metadata.get('description', ''),
            'visibility': metadata.get('visibility', 'public'),
            'tags': metadata.get('tags', []),
            'size': len(file_content),
            'createdAt': timestamp,
            'updatedAt': timestamp
        }
        
        # Store metadata in DynamoDB
        table.put_item(Item=item)
        
        logger.info(f"Image uploaded successfully to {bucket_name}/{object_key} with metadata in {table_name}")
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': 'Image uploaded successfully',
                'id': image_id,
                'filename': metadata['filename'],
                'objectKey': object_key,
                'bucket': bucket_name,
                'contentType': metadata['contentType'],
                'size': len(file_content),
                'userId': metadata['userId']
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        logger.error(f'Error uploading image or storing metadata: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def parse_multipart_form(body, content_type):
    """
    Parse multipart/form-data to extract file and form fields
    
    Args:
        body: The raw body content
        content_type: Content-Type header with boundary
        
    Returns:
        Dictionary with form fields and file data
    """
    try:
        # Extract boundary
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            logger.error("Could not find boundary in content type")
            return None
            
        boundary = boundary_match.group(1)
        
        # Make sure body is bytes
        if isinstance(body, str):
            body = body.encode('utf-8')
            
        # Split the body by boundary
        boundary_bytes = f'--{boundary}'.encode('utf-8')
        parts = body.split(boundary_bytes)
        
        # Skip the first empty part and the last boundary marker
        parts = parts[1:-1]
        
        form_data = {}
        for part in parts:
            # Split headers and content
            try:
                headers_end = part.find(b'\r\n\r\n')
                if headers_end == -1:
                    continue
                    
                headers_raw = part[:headers_end].strip()
                content = part[headers_end + 4:].strip()  # +4 for the double CRLF
                
                # Remove end boundary marker if present
                if content.endswith(b'--\r\n'):
                    content = content[:-4]
                elif content.endswith(b'\r\n'):
                    content = content[:-2]
                    
                # Extract name
                name_match = re.search(rb'name="([^"]+)"', headers_raw)
                if not name_match:
                    continue
                    
                name = name_match.group(1).decode('utf-8')
                
                # Check if this is a file field
                if b'filename=' in headers_raw:
                    filename_match = re.search(rb'filename="([^"]+)"', headers_raw)
                    filename = filename_match.group(1).decode('utf-8') if filename_match else ''
                    
                    # Extract content type if available
                    content_type_match = re.search(rb'Content-Type: ([^\r\n]+)', headers_raw)
                    content_type = content_type_match.group(1).decode('utf-8') if content_type_match else 'application/octet-stream'
                    
                    form_data[name] = {
                        'filename': filename,
                        'content_type': content_type,
                        'content': content
                    }
                else:
                    # Regular form field
                    if isinstance(content, bytes):
                        try:
                            content = content.decode('utf-8')
                        except UnicodeDecodeError:
                            # Keep as bytes if not decodable
                            pass
                    
                    form_data[name] = {'content': content}
                    
            except Exception as e:
                logger.error(f"Error parsing part: {str(e)}")
                continue
                
        return form_data
        
    except Exception as e:
        logger.error(f"Error parsing multipart body: {str(e)}")
        return None

def get_images(event, context):
    """
    List images with filtering options
    
    Supported filters:
    - userId: Filter by user ID
    - tag: Filter by tag
    - visibility: Filter by visibility level (public, private, friends)
    - filename: Filter by filename (partial match)
    - dateFrom: Filter by upload date (from)
    - dateTo: Filter by upload date (to)
    - sort: Sort by field (createdAt, filename)
    - order: Sort order (asc, desc)
    - limit: Limit results
    - nextToken: Pagination token
    
    Args:
        event: HTTP event
        context: Lambda context
        
    Returns:
        HTTP response with image list
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ['IMAGES_TABLE']
        
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Get query string parameters
        query_params = event.get('queryStringParameters', {}) or {}
        user_id = query_params.get('userId')
        tag = query_params.get('tag')
        visibility = query_params.get('visibility', 'public')
        filename = query_params.get('filename')
        date_from = query_params.get('dateFrom')
        date_to = query_params.get('dateTo')
        sort_by = query_params.get('sort', 'createdAt')
        sort_order = query_params.get('order', 'desc').lower()
        limit = int(query_params.get('limit', 10))
        next_token = query_params.get('nextToken')
        
        # Validate parameters
        if limit < 1 or limit > 100:
            limit = 10
            
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
            
        # Build the scan parameters
        scan_params = {
            'Limit': limit
        }
        
        # Add pagination token if provided
        if next_token:
            try:
                scan_params['ExclusiveStartKey'] = json.loads(
                    base64.b64decode(next_token).decode('utf-8')
                )
            except Exception as e:
                logger.error(f"Invalid pagination token: {str(e)}")
        
        # Initialize expressions and attribute values
        filter_expressions = []
        expression_attribute_values = {}
        
        # Filter by userId if provided
        if user_id:
            filter_expressions.append("userId = :userId")
            expression_attribute_values[':userId'] = user_id
            
        # Filter by visibility
        if visibility and visibility != 'all':
            filter_expressions.append("visibility = :visibility")
            expression_attribute_values[':visibility'] = visibility
            
        # Filter by filename (partial match) if provided
        if filename:
            filter_expressions.append("contains(filename, :filename)")
            expression_attribute_values[':filename'] = filename
            
        # Filter by upload date range if provided
        if date_from:
            try:
                # Convert to ISO string for comparison
                date_from_iso = datetime.fromisoformat(date_from).isoformat()
                filter_expressions.append("createdAt >= :dateFrom")
                expression_attribute_values[':dateFrom'] = date_from_iso
            except ValueError:
                logger.warning(f"Invalid dateFrom format: {date_from}")
                
        if date_to:
            try:
                # Convert to ISO string for comparison
                date_to_iso = datetime.fromisoformat(date_to).isoformat()
                filter_expressions.append("createdAt <= :dateTo")
                expression_attribute_values[':dateTo'] = date_to_iso
            except ValueError:
                logger.warning(f"Invalid dateTo format: {date_to}")
        
        # Combine filter expressions if any
        if filter_expressions:
            scan_params['FilterExpression'] = " AND ".join(filter_expressions)
            scan_params['ExpressionAttributeValues'] = expression_attribute_values
            
        # Execute the query
        response = table.scan(**scan_params)
        items = response.get('Items', [])
        
        # Filter by tag if provided (in-memory filter since DynamoDB doesn't support direct array contains)
        if tag and items:
            items = [item for item in items if tag in (item.get('tags', []))]
            
        # Sort results
        if sort_by:
            reverse = sort_order == 'desc'
            items = sorted(
                items, 
                key=lambda x: x.get(sort_by, ''), 
                reverse=reverse
            )
        
        # Handle pagination
        result = {
            'images': items,
            'count': len(items)
        }
        
        # Include pagination token if more results available
        if 'LastEvaluatedKey' in response:
            result['nextToken'] = base64.b64encode(
                json.dumps(response['LastEvaluatedKey'], cls=DecimalEncoder).encode('utf-8')
            ).decode('utf-8')
            
        # Return the results
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, cls=DecimalEncoder)
        }
        
    except Exception as e:
        logger.error(f'Error listing images: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def get_image(event, context):
    """
    Get a single image metadata by ID
    
    Args:
        event: HTTP event
        context: Lambda context
        
    Returns:
        HTTP response with image metadata
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ['IMAGES_TABLE']
        
        # Get the image ID from path parameters
        image_id = event.get('pathParameters', {}).get('id')
        if not image_id:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image ID is required'})
            }
            
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Get the image metadata
        result = table.get_item(Key={'id': image_id})
        
        if 'Item' not in result:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image not found'})
            }
            
        # Return the image metadata
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result['Item'], cls=DecimalEncoder)
        }
        
    except Exception as e:
        logger.error(f'Error getting image: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def delete_image(event, context):
    """
    Delete an image and its metadata
    
    Args:
        event: HTTP event
        context: Lambda context
        
    Returns:
        HTTP response
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ['IMAGES_TABLE']
        bucket_name = os.environ['S3_BUCKET']
        
        # Get the image ID from path parameters
        image_id = event.get('pathParameters', {}).get('id')
        if not image_id:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image ID is required'})
            }
            
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Get the image metadata to retrieve the object key
        result = table.get_item(Key={'id': image_id})
        
        if 'Item' not in result:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image not found'})
            }
            
        # Get the object key
        object_key = result['Item'].get('objectKey')
        
        # Delete the image from S3
        s3_client = get_s3_client()
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=object_key
        )
        
        # Delete the metadata from DynamoDB
        table.delete_item(Key={'id': image_id})
        
        # Return success response
        return {
            'statusCode': 204,
            'body': json.dumps({})
        }
        
    except Exception as e:
        logger.error(f'Error deleting image: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def update_image_metadata(event, context):
    """
    Update image metadata
    
    Args:
        event: HTTP event
        context: Lambda context
        
    Returns:
        HTTP response with updated metadata
    """
    try:
        # Extract table name from environment variables
        table_name = os.environ['IMAGES_TABLE']
        
        # Get the image ID from path parameters
        image_id = event.get('pathParameters', {}).get('id')
        if not image_id:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image ID is required'})
            }
            
        # Parse request body
        body = json.loads(event['body'])
        
        # Initialize DynamoDB client
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Get the current image metadata
        result = table.get_item(Key={'id': image_id})
        
        if 'Item' not in result:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Image not found'})
            }
            
        # Fields that can be updated
        updateable_fields = ['description', 'visibility', 'tags']
        
        # Build update expression
        update_expression = "SET updatedAt = :updatedAt"
        expression_attribute_values = {
            ':updatedAt': datetime.utcnow().isoformat()
        }
        expression_attribute_names = {}
        
        # Add fields to update expression
        for field in updateable_fields:
            if field in body:
                update_expression += f", #{field} = :{field}"
                expression_attribute_values[f":{field}"] = body[field]
                expression_attribute_names[f"#{field}"] = field
        
        # If no fields to update
        if len(expression_attribute_values) == 1:  # Only updatedAt
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'No fields to update'})
            }
            
        # Update the metadata in DynamoDB
        update_response = table.update_item(
            Key={'id': image_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues='ALL_NEW'
        )
        
        # Return the updated metadata
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(update_response['Attributes'], cls=DecimalEncoder)
        }
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        logger.error(f'Error updating image metadata: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

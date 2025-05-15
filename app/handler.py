import json
import os
import uuid
from datetime import datetime
import boto3
from jsonschema import validate, ValidationError

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

# Define schemas
ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "minLength": 1}
    },
    "required": ["content"],
    "additionalProperties": False
}

def validate_against_schema(data, schema):
    """Validate data against a schema"""
    try:
        validate(instance=data, schema=schema)
        return None
    except ValidationError as e:
        return str(e)

def router(event, context):
    """Router function that handles all API endpoints"""
    
    method = event['httpMethod']
    path = event['path']
    
    # Get the ID from path parameters if it exists
    path_parameters = event.get('pathParameters', {}) or {}
    item_id = path_parameters.get('id')
    
    # Route the request to the appropriate handler
    if method == 'POST' and path == '/items':
        return create_item_handler(event, context)
    elif method == 'GET' and item_id:
        return get_item_handler(event, context, item_id)
    elif method == 'GET' and path == '/items':
        return list_items_handler(event, context)
    elif method == 'PUT' and item_id:
        return update_item_handler(event, context, item_id)
    elif method == 'DELETE' and item_id:
        return delete_item_handler(event, context, item_id)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not Found'})
        }

def create_item_handler(event, context):
    # Implementation for creating an item
    data = json.loads(event['body'])
    
    # Validate data against schema
    validation_error = validate_against_schema(data, ITEM_SCHEMA)
    if validation_error:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': validation_error})
        }
    
    timestamp = datetime.utcnow().isoformat()
    item = {
        'id': str(uuid.uuid4()),
        'content': data.get('content'),
        'createdAt': timestamp,
        'updatedAt': timestamp,
    }
    
    table.put_item(Item=item)
    
    return {
        'statusCode': 201,
        'body': json.dumps(item)
    }

def get_item_handler(event, context, item_id):
    # Implementation for getting a single item
    result = table.get_item(Key={'id': item_id})
    
    if 'Item' in result:
        return {
            'statusCode': 200,
            'body': json.dumps(result['Item'])
        }
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Item not found'})
        }

def list_items_handler(event, context):
    # Implementation for listing all items
    result = table.scan()
    
    return {
        'statusCode': 200,
        'body': json.dumps(result['Items'])
    }

def update_item_handler(event, context, item_id):
    # Implementation for updating an item
    data = json.loads(event['body'])
    
    # Validate data against schema
    validation_error = validate_against_schema(data, ITEM_SCHEMA)
    if validation_error:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': validation_error})
        }
    
    timestamp = datetime.utcnow().isoformat()
    
    result = table.update_item(
        Key={'id': item_id},
        ExpressionAttributeNames={
            '#content': 'content',
        },
        ExpressionAttributeValues={
            ':content': data['content'],
            ':updatedAt': timestamp,
        },
        UpdateExpression='SET #content = :content, updatedAt = :updatedAt',
        ReturnValues='ALL_NEW',
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps(result['Attributes'])
    }

def delete_item_handler(event, context, item_id):
    # Implementation for deleting an item
    table.delete_item(Key={'id': item_id})
    
    return {
        'statusCode': 204,
        'body': json.dumps({})
    }
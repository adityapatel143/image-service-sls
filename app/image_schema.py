"""
Image metadata schema definition for validation
"""

# Schema for image metadata validation
IMAGE_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "userId": {"type": "string", "minLength": 1},
        "visibility": {"type": "string", "enum": ["public", "private", "friends"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"}
        },
        "contentType": {"type": "string", "minLength": 1}
    },
    "required": ["filename", "userId", "contentType"],
    "additionalProperties": True
}

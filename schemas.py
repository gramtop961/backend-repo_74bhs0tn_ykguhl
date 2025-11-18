"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    username: str = Field(..., description="Unique handle")
    display_name: Optional[str] = Field(None, description="Name shown publicly")
    bio: Optional[str] = Field(None, description="Short bio")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")

class Post(BaseModel):
    """
    Posts collection schema
    Collection name: "post"
    """
    username: str = Field(..., description="Owner username")
    image_url: str = Field(..., description="Public URL of uploaded image")
    caption: Optional[str] = Field(None, description="User-provided caption")
    public: bool = Field(True, description="Whether visible in public feed")

    # Non-judgmental visual analysis attributes
    palette: List[str] = Field(default_factory=list, description="Top HEX colors in the image")
    energy: float = Field(0.0, ge=0.0, le=1.0, description="Relative visual energy 0-1 based on saturation/contrast")
    warmth: float = Field(0.0, ge=0.0, le=1.0, description="Relative color warmth 0-1 (cool→warm)")
    contrast: float = Field(0.0, ge=0.0, le=1.0, description="Relative contrast 0-1")
    tags: List[str] = Field(default_factory=list, description="Non-judgmental style descriptors")
    vibe_index: float = Field(0.0, ge=0.0, le=10.0, description="Composite style index 0-10 derived from visual attributes")

class Like(BaseModel):
    """
    Likes collection schema
    Collection name: "like"
    """
    post_id: str = Field(..., description="ID of the liked post")
    username: str = Field(..., description="Username who liked the post")

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import io
import requests
from PIL import Image

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ Utilities ------------

def to_str_id(doc):
    if not doc:
        return doc
    d = dict(doc)
    if d.get("_id") is not None:
        d["id"] = str(d.pop("_id"))
    # Convert datetime to isoformat
    for k, v in list(d.items()):
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


def extract_palette_and_metrics(image: Image.Image, num_colors: int = 5):
    # Resize for speed
    img = image.convert('RGB').copy()
    img.thumbnail((256, 256))

    # Get colors
    # Using quantize to reduce to dominant colors
    pal = img.quantize(colors=num_colors, method=Image.MEDIANCUT)
    palette = pal.getpalette()[:num_colors * 3]
    colors = []
    for i in range(num_colors):
        r = palette[i*3]
        g = palette[i*3+1]
        b = palette[i*3+2]
        colors.append(f"#{r:02x}{g:02x}{b:02x}")

    # Compute simple metrics
    px = img.load()
    w, h = img.size
    total = w * h
    # average brightness and contrast proxy
    sum_l = 0
    sum_l2 = 0
    sum_warm = 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r, g, b = px[x, y]
            l = 0.2126*r + 0.7152*g + 0.0722*b
            sum_l += l
            sum_l2 += l*l
            # simple warmth proxy: red vs blue
            sum_warm += max(0, r - b)
    n = (w//4+ (1 if w%4 else 0)) * (h//4+ (1 if h%4 else 0))
    if n == 0:
        n = 1
    avg_l = sum_l / n
    var_l = max(0.0, sum_l2 / n - avg_l*avg_l)
    contrast = min(1.0, var_l / (255*255/4))
    warmth = min(1.0, sum_warm / (n*255))

    # energy proxy via saturation: convert a few samples to HSV-like
    def sat(r, g, b):
        mx = max(r, g, b)
        mn = min(r, g, b)
        return 0 if mx == 0 else (mx - mn) / mx
    sum_sat = 0
    count = 0
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            r, g, b = px[x, y]
            sum_sat += sat(r, g, b)
            count += 1
    energy = 0 if count == 0 else min(1.0, sum_sat / count)

    # Composite vibe index 0-10
    vibe_index = round(10 * (0.4*energy + 0.3*contrast + 0.3*warmth), 2)

    # Non-judgmental descriptors
    tags = []
    tags.append('warm' if warmth > 0.5 else 'cool')
    tags.append('high-contrast' if contrast > 0.5 else 'soft-contrast')
    tags.append('vibrant' if energy > 0.5 else 'muted')

    return {
        'palette': colors,
        'energy': round(float(energy), 3),
        'warmth': round(float(warmth), 3),
        'contrast': round(float(contrast), 3),
        'tags': tags,
        'vibe_index': vibe_index
    }


# ------------ Models ------------

class CreateUser(BaseModel):
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

class AnalyzeImageRequest(BaseModel):
    image_url: str

class CreatePostRequest(BaseModel):
    username: str = Field(...)
    image_url: str
    caption: Optional[str] = None
    public: bool = True

class PostResponse(BaseModel):
    id: str
    username: str
    image_url: str
    caption: Optional[str]
    public: bool
    palette: List[str]
    energy: float
    warmth: float
    contrast: float
    tags: List[str]
    vibe_index: float
    created_at: Optional[str] = None


# ------------ Routes ------------

@app.get("/")
def read_root():
    return {"message": "Vibe Feed API Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
    }
    try:
        if db is not None:
            _ = db.list_collection_names()
            response["database"] = "✅ Connected"
        else:
            response["database"] = "❌ Not Configured"
    except Exception as e:
        response["database"] = f"⚠️ {str(e)[:80]}"
    return response

@app.post("/api/users")
def create_user(payload: CreateUser):
    if db is None:
        raise HTTPException(500, "Database not configured")
    # ensure uniqueness by username
    existing = db['user'].find_one({"username": payload.username})
    if existing:
        raise HTTPException(400, "Username already exists")
    user_id = create_document('user', payload.dict())
    doc = db['user'].find_one({"_id": ObjectId(user_id)})
    return to_str_id(doc)

@app.post("/api/posts/analyze")
def analyze_image(req: AnalyzeImageRequest):
    try:
        r = requests.get(req.image_url, timeout=10)
        r.raise_for_status()
        image = Image.open(io.BytesIO(r.content))
    except Exception as e:
        raise HTTPException(400, f"Unable to fetch or parse image: {str(e)[:80]}")
    metrics = extract_palette_and_metrics(image)
    # Also generate simple descriptors sentence
    descriptors = [*metrics['tags']]
    return {**metrics, 'descriptors': descriptors}

@app.post("/api/posts", response_model=PostResponse)
def create_post(payload: CreatePostRequest):
    if db is None:
        raise HTTPException(500, "Database not configured")
    # analyze image
    try:
        r = requests.get(payload.image_url, timeout=10)
        r.raise_for_status()
        image = Image.open(io.BytesIO(r.content))
    except Exception as e:
        raise HTTPException(400, f"Unable to fetch or parse image: {str(e)[:80]}")
    metrics = extract_palette_and_metrics(image)

    data = {
        "username": payload.username,
        "image_url": payload.image_url,
        "caption": payload.caption,
        "public": payload.public,
        **metrics,
    }
    post_id = create_document('post', data)
    doc = db['post'].find_one({"_id": ObjectId(post_id)})
    doc = to_str_id(doc)
    return PostResponse(**doc)  # type: ignore

@app.get("/api/posts")
def list_posts(limit: int = 50, sort: str = "top"):
    if db is None:
        raise HTTPException(500, "Database not configured")
    cursor = db['post'].find({"public": True})
    if sort == 'top':
        cursor = cursor.sort("vibe_index", -1)
    else:
        cursor = cursor.sort("created_at", -1)
    cursor = cursor.limit(min(limit, 100))
    items = [to_str_id(x) for x in cursor]
    return {"items": items}

@app.get("/api/rankings/top")
def rankings_top(limit: int = 20):
    cursor = db['post'].find({"public": True}).sort("vibe_index", -1).limit(min(limit, 100))
    items = [to_str_id(x) for x in cursor]
    return {"items": items}


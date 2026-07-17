import os
import re
from collections import Counter
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime

STOPWORDS = {
    'the','and','for','with','that','this','from','your','their','have','been',
    'will','just','when','where','what','which','who','whom','more','some','such',
    'about','also','into','over','under','before','after','while','being','while',
    'about','these','those','there','every','other','while','among','through',
    'since','until','than','each','both','few','many','most','much','each','else',
    'into','using','used','use','photo','image','picture','memory','memories',
    'trip','day','days','one','two','new','old','back','time','times','nice',
    'good','best','great','very','really','also','still','even'
}

def extract_keywords_from_text(text, top_n=4):
    if not text:
        return []

    normalized = text.lower()
    words = re.findall(r"[a-z0-9]{3,}", normalized)
    filtered = [w for w in words if w not in STOPWORDS]
    if not filtered:
        return []

    counts = Counter(filtered)
    sorted_words = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    keywords = [word for word, _ in sorted_words][:top_n]
    return keywords


def get_decimal_from_dms(dms, ref):
    try:
        degrees = dms[0]
        minutes = dms[1]
        seconds = dms[2]
        
        # Pillow might return Rational objects, convert to floats
        deg = float(degrees)
        min_val = float(minutes)
        sec = float(seconds)
        
        decimal = deg + (min_val / 60.0) + (sec / 3600.0)
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception:
        return None

def extract_exif_metadata(image_file):
    metadata = {
        'captured_at': None,
        'camera_model': '',
        'location': ''
    }
    
    if not image_file:
        return metadata

    try:
        from pathlib import Path
        if isinstance(image_file, (str, Path)):
            if not os.path.exists(image_file):
                return metadata
            with Image.open(image_file) as img:
                exif = img._getexif()
        else:
            file_obj = None
            if hasattr(image_file, 'open'):
                try:
                    image_file.open('rb')
                except Exception:
                    pass
            if hasattr(image_file, 'file'):
                file_obj = image_file.file
            else:
                file_obj = image_file
            try:
                file_obj.seek(0)
            except Exception:
                pass
            with Image.open(file_obj) as img:
                exif = img._getexif()
        
        if not exif:
            return metadata
        
        exif_data = {}
        for tag, value in exif.items():
            decoded = TAGS.get(tag, tag)
            exif_data[decoded] = value
        
        # 1. Camera model
        if 'Model' in exif_data:
            metadata['camera_model'] = str(exif_data['Model']).strip()
            
        # 2. Date Taken
        # Try DateTimeOriginal, then DateTimeDigitized, then DateTime
        for tag_name in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
            if tag_name in exif_data:
                dt_str = str(exif_data[tag_name]).strip()
                try:
                    # Standard EXIF date format is YYYY:MM:DD HH:MM:SS
                    metadata['captured_at'] = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                    break
                except ValueError:
                    pass
        
        # 3. GPS Info
        if 'GPSInfo' in exif_data:
            gps_info = {}
            for key, val in exif_data['GPSInfo'].items():
                decoded = GPSTAGS.get(key, key)
                gps_info[decoded] = val
            
            lat = gps_info.get('GPSLatitude')
            lat_ref = gps_info.get('GPSLatitudeRef')
            lng = gps_info.get('GPSLongitude')
            lng_ref = gps_info.get('GPSLongitudeRef')
            
            if lat and lat_ref and lng and lng_ref:
                dec_lat = get_decimal_from_dms(lat, lat_ref)
                dec_lng = get_decimal_from_dms(lng, lng_ref)
                if dec_lat is not None and dec_lng is not None:
                    metadata['location'] = f"{dec_lat:.6f}, {dec_lng:.6f}"
                        
    except Exception as e:
        print(f"Error parsing EXIF: {e}")
        
    return metadata


RECALL_INTENT_PATTERN = re.compile(
    r'\b(recall|show|see|find|display|memory|memories|gallery|photo|photos|picture|pictures|image|images)\b',
    re.IGNORECASE,
)

GENERIC_PROMPT_WORDS = {
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'your', 'have', 'been',
    'will', 'what', 'when', 'where', 'which', 'about', 'also', 'into', 'over',
    'show', 'tell', 'give', 'please', 'want', 'need', 'help', 'recall', 'memory',
    'memories', 'gallery', 'photo', 'photos', 'picture', 'pictures', 'image', 'images',
    'see', 'find', 'display', 'from', 'are', 'was', 'were', 'any', 'all', 'some',
}


def _prompt_keywords(prompt):
    words = [w.strip(',.?!"\'').lower() for w in prompt.split() if len(w.strip(',.?!"\'')) > 2]
    return [w for w in words if w not in GENERIC_PROMPT_WORDS]


def find_matching_images(user, prompt, limit=3):
    from .models import ImageMemory

    images = list(
        ImageMemory.objects.filter(user=user)
        .only('description', 'location', 'tags', 'filename', 'image')
        .order_by('-uploaded_at')
    )
    if not images:
        return []

    keywords = _prompt_keywords(prompt)
    scored = []

    for img in images:
        score = 0
        desc = (img.description or "").lower()
        loc = (img.location or "").lower()
        tags = [t.strip().lower() for t in (img.tags or "").split(',') if t.strip()]
        filename = img.filename.lower()
        haystack = " ".join([desc, loc, filename, " ".join(tags)])

        for word in keywords:
            if word in haystack:
                score += 2
            if word in desc:
                score += 3
            if word in loc:
                score += 4
            if word in filename:
                score += 2
            if any(word in tag or tag in word for tag in tags):
                score += 5

        if score > 0:
            scored.append((score, img))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [img for _, img in scored[:limit]]

    if RECALL_INTENT_PATTERN.search(prompt):
        return images[:limit]

    return []


def format_image_recall_markdown(images):
    lines = []
    for img in images:
        desc = img.description or img.filename
        lines.append(f"![{desc}]({img.image.url})")
    return "\n\n".join(lines)


def get_image_context(user, prompt):
    matched = find_matching_images(user, prompt)
    if not matched:
        return ""

    context_str = (
        "\nMatched images from user memories database. "
        "You MUST include each matched image in your reply using the exact markdown shown below:\n"
    )
    for img in matched:
        url = img.image.url
        tags_str = img.tags or "None"
        loc_str = img.location or "None"
        desc_str = img.description or img.filename
        context_str += (
            f"- Image description: {desc_str} | Tags: {tags_str} | Location: {loc_str} "
            f"| Markdown Tag: ![{desc_str}]({url})\n"
        )
    return context_str


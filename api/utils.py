import os
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime

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
            try:
                image_file.seek(0)
            except Exception:
                pass
            with Image.open(image_file) as img:
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


def get_image_context(user, prompt):
    from .models import ImageMemory
    # Look up images for user
    images = ImageMemory.objects.filter(user=user)
    
    # Tokenize prompt to find matching tags/location/description
    words = [w.strip(',.?!"\'').lower() for w in prompt.split() if len(w.strip(',.?!"\'')) > 2]
    
    matched_images = []
    for img in images:
        score = 0
        desc = (img.description or "").lower()
        loc = (img.location or "").lower()
        tags = [t.strip().lower() for t in (img.tags or "").split(',') if t.strip()]
        filename = img.filename.lower()
        
        for word in words:
            if word in desc:
                score += 3
            if word in loc:
                score += 4
            if word in filename:
                score += 2
            if any(word in t for t in tags):
                score += 5
        
        if score > 0:
            matched_images.append((score, img))
            
    # Sort by score descending
    matched_images.sort(key=lambda x: x[0], reverse=True)
    
    if matched_images:
        context_str = "\nMatched images from user memories database. If user asks to see/recall an image matching these details, present it using markdown format `![caption](url)`:\n"
        for score, img in matched_images[:3]: # top 3 matches
            url = img.image.url
            tags_str = img.tags or "None"
            loc_str = img.location or "None"
            desc_str = img.description or img.filename
            context_str += f"- Image description: {desc_str} | Tags: {tags_str} | Location: {loc_str} | Markdown Tag: ![{desc_str}]({url})\n"
        return context_str
    return ""


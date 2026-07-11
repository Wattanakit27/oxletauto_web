"""ดึงรีวิวจาก Google Places API (legacy Place Details)
หมายเหตุ: Google คืนรีวิวได้สูงสุด 5 รีวิว/สถานที่ (ลิมิตของ Google เอง)
ต้องเปิด "Places API" ใน Google Cloud + ใส่ GOOGLE_MAPS_API_KEY ใน .env
"""
import json
import urllib.parse
import urllib.request

ENDPOINT = "https://maps.googleapis.com/maps/api/place/details/json"


def fetch_place(place_id, api_key, language="th"):
    """คืน dict: {ok, rating, total, maps_url, reviews:[...]} หรือ {ok:False, error}"""
    if not api_key or not place_id:
        return {"ok": False, "error": "ไม่มี API key หรือ Place ID"}

    params = {
        "place_id": place_id,
        "fields": "rating,user_ratings_total,url,reviews,geometry/location",
        "reviews_sort": "newest",
        "language": language,
        "key": api_key,
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"เรียก API ไม่สำเร็จ: {e}"}

    if data.get("status") != "OK":
        return {"ok": False, "error": data.get("status") + " " + data.get("error_message", "")}

    res = data["result"]
    reviews = []
    for rv in res.get("reviews", []):
        reviews.append({
            "external_id": f"{place_id}:{rv.get('time')}:{rv.get('author_name','')}",
            "time": rv.get("time"),
            "author": rv.get("author_name", ""),
            "rating": rv.get("rating", 5),
            "text": rv.get("text", ""),
            "photo": rv.get("profile_photo_url", ""),
            "url": rv.get("author_url", ""),
            "relative_time": rv.get("relative_time_description", ""),
        })
    loc = res.get("geometry", {}).get("location", {})
    return {
        "ok": True,
        "rating": res.get("rating"),
        "total": res.get("user_ratings_total", 0),
        "maps_url": res.get("url", ""),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "reviews": reviews,
    }

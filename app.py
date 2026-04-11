"""
FarmWise AI - Stable Working Version
Features: Live weather (all 16 Ghana regions), AI chat, Photo diagnosis, Twi language

Run:
    pip install flask anthropic requests gunicorn
    export ANTHROPIC_API_KEY=sk-ant-your-key-here
    python app.py
"""

import os
import json
import requests
import anthropic
from flask import Flask, render_template, request, jsonify, stream_with_context, Response

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

SYSTEM_PROMPT_EN = """You are FarmWise AI, a knowledgeable and friendly farming assistant focused on 
helping smallholder farmers in Ghana and West Africa. You help with:

1. WEATHER & IRRIGATION - interpreting weather patterns, advising on irrigation timing, 
   planting windows, and climate risks for local crops.
2. MARKET PRICES - advising on when to buy inputs, when to sell harvests, price trends 
   for maize, cassava, tomatoes, plantain, yam, cocoa, and other Ghanaian crops.
3. PEST & DISEASE MANAGEMENT - identifying symptoms, recommending affordable local 
   treatments, and preventive practices for common pests like Fall Armyworm, aphids, 
   leaf blight, and cassava mosaic virus.
4. CROP PLANNING - which crops suit the season, soil type, rainfall; rotation advice.

Always give practical, affordable advice suited to smallholder farming with limited resources.
Be concise, clear, and warm. Use simple language. When relevant, mention local crop names 
and local markets (Kumasi, Accra, Tamale). If a question is outside farming, gently redirect 
back to farming topics.
"""

SYSTEM_PROMPT_TW = """Wo yɛ FarmWise AI, obi a ɔnim adwuma ho asɛm na ɔboa nnomkuo afuom adwumayɛfoɔ 
wɔ Ghana ne Atɔeɛ Afrika mu. Woboa wɔn ho asɛm a ɛfa ɔhaw, aguadi, mmoa ne aba dua.
Ka asɛm no ntɛm, dwoodwoo, na sɔ wɔn da. Fa kasa a ɛyɛ mmerɛw.
"""

DISEASE_PROMPT_EN = """You are an expert plant pathologist for Ghana and West Africa crops.
Analyze this crop photo and provide:
1. DISEASE/PEST NAME - what you see affecting the crop
2. CROP AFFECTED - identify the crop if visible
3. SEVERITY - Low / Medium / High
4. SYMPTOMS - what visible signs you can see in the image
5. TREATMENT - affordable, practical treatment steps for Ghana smallholder farmers
6. PREVENTION - how to prevent this in future
Be specific and mention locally available products where possible.
If the image is not a crop or plant, politely say so.
"""

DISEASE_PROMPT_TW = """Wo yɛ ogya a ɔnim aba yareɛ wɔ Ghana ne Atɔeɛ Afrika afuo mu.
Hwɛ saa foto yi na ka: yareɛ din, aba a ɛwɔ so, yareɛ tenten, nsɛnkyerɛnne, aduro, ne banbɔ.
"""

# ---------------------------------------------------------------------------
# Ghana regions
# ---------------------------------------------------------------------------
GHANA_REGIONS = {
    "greater_accra":  {"name": "Greater Accra (Accra)",        "name_tw": "Accra Kuro",             "lat": 5.55,  "lon": -0.20},
    "ashanti":        {"name": "Ashanti (Kumasi)",              "name_tw": "Ashanti (Kumasi)",        "lat": 6.69,  "lon": -1.62},
    "northern":       {"name": "Northern (Tamale)",             "name_tw": "Atifi (Tamale)",          "lat": 9.40,  "lon": -0.85},
    "central":        {"name": "Central (Cape Coast)",          "name_tw": "Mfinimfini (Cape Coast)", "lat": 5.10,  "lon": -1.25},
    "bono":           {"name": "Bono (Sunyani)",                "name_tw": "Bono (Sunyani)",          "lat": 7.33,  "lon": -2.33},
    "eastern":        {"name": "Eastern (Koforidua)",           "name_tw": "Apuei (Koforidua)",       "lat": 6.09,  "lon": -0.26},
    "volta":          {"name": "Volta (Ho)",                    "name_tw": "Volta (Ho)",              "lat": 6.60,  "lon":  0.47},
    "upper_west":     {"name": "Upper West (Wa)",               "name_tw": "Atifi Atɔeɛ (Wa)",       "lat": 10.06, "lon": -2.50},
    "upper_east":     {"name": "Upper East (Bolgatanga)",       "name_tw": "Atifi Apuei (Bolgatanga)","lat": 10.79, "lon": -0.85},
    "western":        {"name": "Western (Takoradi)",            "name_tw": "Atɔeɛ (Takoradi)",       "lat": 4.90,  "lon": -1.76},
    "oti":            {"name": "Oti (Dambai)",                  "name_tw": "Oti (Dambai)",            "lat": 7.97,  "lon":  0.18},
    "bono_east":      {"name": "Bono East (Techiman)",          "name_tw": "Bono Apuei (Techiman)",   "lat": 7.59,  "lon": -1.94},
    "ahafo":          {"name": "Ahafo (Goaso)",                 "name_tw": "Ahafo (Goaso)",           "lat": 6.80,  "lon": -2.52},
    "western_north":  {"name": "Western North (Sefwi Wiawso)", "name_tw": "Atɔeɛ Atifi (Sefwi)",    "lat": 6.20,  "lon": -2.47},
    "north_east":     {"name": "North East (Nalerigu)",         "name_tw": "Atifi Apuei (Nalerigu)",  "lat": 10.52, "lon": -0.36},
    "savannah":       {"name": "Savannah (Damongo)",            "name_tw": "Savannah (Damongo)",      "lat": 9.08,  "lon": -1.82},
}

# ---------------------------------------------------------------------------
# Live weather — with caching to avoid rate limits
# ---------------------------------------------------------------------------
_weather_cache = {}

def get_weather(region_key="greater_accra"):
    region = GHANA_REGIONS.get(region_key, GHANA_REGIONS["greater_accra"])

    # Return cached data if less than 30 minutes old
    import time
    cache_entry = _weather_cache.get(region_key)
    if cache_entry and (time.time() - cache_entry["ts"]) < 1800:
        return cache_entry["data"]

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={region['lat']}&longitude={region['lon']}"
            f"&daily=temperature_2m_max,precipitation_probability_max,windspeed_10m_max"
            f"&hourly=relativehumidity_2m"
            f"&forecast_days=7"
            f"&timezone=Africa%2FAccra"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        daily     = data["daily"]
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        def rain_icon(pct):
            if pct < 30:   return "☀️"
            elif pct < 60: return "⛅"
            else:          return "🌧️"

        forecast = [
            {
                "day":  day_names[i % 7],
                "icon": rain_icon(daily["precipitation_probability_max"][i]),
                "high": round(daily["temperature_2m_max"][i]),
                "rain": daily["precipitation_probability_max"][i],
            }
            for i in range(min(7, len(daily["temperature_2m_max"])))
        ]

        today_rain = daily["precipitation_probability_max"][0]
        today_high = round(daily["temperature_2m_max"][0])
        today_wind = round(daily["windspeed_10m_max"][0])
        humidity   = data["hourly"]["relativehumidity_2m"][12]

        if today_rain >= 70:
            advice     = f"Heavy rain expected in {region['name']}. Avoid spraying pesticides. Check field drainage."
            advice_tw  = f"Osu kɛseɛ reba wɔ {region['name_tw']}. Mma aduro gu afuo so."
            risk       = "High flood / waterlogging risk"
            risk_tw    = "Osu kɛseɛ tumi de ɔhaw ba"
            risk_level = "danger"
        elif today_rain >= 40:
            advice     = f"Moderate rain likely in {region['name']}. Skip irrigation on rainy days."
            advice_tw  = f"Osu kakra reba wɔ {region['name_tw']}. Mma nsuo gu afuo so da a osu ba."
            risk       = "Moderate moisture stress risk"
            risk_tw    = "Nsuo haw mfinimfini"
            risk_level = "warn"
        else:
            advice     = f"Dry conditions in {region['name']}. Irrigate crops well, especially seedlings."
            advice_tw  = f"Awia bɛyɛ den wɔ {region['name_tw']}. Ma nsuo gu wo aba so."
            risk       = "Low rainfall — monitor soil moisture"
            risk_tw    = "Osu ketewa — hwɛ asaase nsuo"
            risk_level = "ok"

        result = {
            "location":    region["name"],
            "location_tw": region["name_tw"],
            "today_high":  today_high,
            "humidity":    humidity,
            "rain_chance": today_rain,
            "wind_kmh":    today_wind,
            "forecast":    forecast,
            "advice":      advice,
            "advice_tw":   advice_tw,
            "risk":        risk,
            "risk_tw":     risk_tw,
            "risk_level":  risk_level,
            "live":        True,
        }

        _weather_cache[region_key] = {"ts": time.time(), "data": result}
        return result

    except Exception as e:
        print(f"[Weather error] {e}")
        # Return cached data even if stale, rather than failing
        if cache_entry:
            return cache_entry["data"]
        return {
            "location":    region["name"],
            "location_tw": region["name_tw"],
            "today_high":  34,
            "humidity":    78,
            "rain_chance": 60,
            "wind_kmh":    14,
            "forecast": [
                {"day": "Mon", "icon": "☀️",  "high": 34, "rain": 10},
                {"day": "Tue", "icon": "⛅",  "high": 33, "rain": 30},
                {"day": "Wed", "icon": "🌧️", "high": 29, "rain": 75},
                {"day": "Thu", "icon": "🌧️", "high": 28, "rain": 80},
                {"day": "Fri", "icon": "⛅",  "high": 31, "rain": 40},
                {"day": "Sat", "icon": "☀️",  "high": 33, "rain": 15},
                {"day": "Sun", "icon": "☀️",  "high": 34, "rain": 10},
            ],
            "advice":      "Weather data temporarily unavailable. Please check back shortly.",
            "advice_tw":   "Ɔhaw ho nsɛm nni hɔ seesei.",
            "risk":        "Data unavailable",
            "risk_tw":     "Nsɛm nni hɔ",
            "risk_level":  "warn",
            "live":        False,
        }

# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------
PRICE_DATA = [
    {"crop": "Maize",     "crop_tw": "Aburo",   "unit": "50kg bag",    "price": 240, "change": 8,   "trend": "up"},
    {"crop": "Tomatoes",  "crop_tw": "Ntomato", "unit": "crate",       "price": 180, "change": -12, "trend": "down"},
    {"crop": "Cassava",   "crop_tw": "Bankye",  "unit": "100kg bag",   "price": 310, "change": 0,   "trend": "stable"},
    {"crop": "Plantain",  "crop_tw": "Ɔgede",   "unit": "bunch",       "price": 55,  "change": 3,   "trend": "up"},
    {"crop": "Yam",       "crop_tw": "Bayerɛ",  "unit": "tuber (lg)",  "price": 35,  "change": 5,   "trend": "up"},
    {"crop": "Cocoa",     "crop_tw": "Kookoo",  "unit": "kg dry bean", "price": 24,  "change": 2,   "trend": "up"},
    {"crop": "Pepper",    "crop_tw": "Mako",    "unit": "kg",          "price": 28,  "change": -5,  "trend": "down"},
    {"crop": "Groundnut", "crop_tw": "Nkatie",  "unit": "50kg bag",    "price": 290, "change": 1,   "trend": "stable"},
]

PEST_DATA = [
    {
        "name": "Fall Armyworm",       "name_tw": "Aburo Mmoa",
        "crops": "Maize",              "crops_tw": "Aburo",
        "description": "High risk season. Check leaves for feeding damage and egg masses.",
        "description_tw": "Ɔberɛ kɛseɛ. Hwɛ nkotokuo so sɛ mmoa adidi so.",
        "level": "high",
        "tip": "Apply neem-based spray early morning. Report sightings to extension officer.",
        "tip_tw": "De neem aduro gu so anɔpa.",
    },
    {
        "name": "Cassava Leaf Blight", "name_tw": "Bankye Nkotokuo Yareɛ",
        "crops": "Cassava",            "crops_tw": "Bankye",
        "description": "Humidity-driven fungal disease. Angular brown spots on leaves.",
        "description_tw": "Yareɛ a nsuo ɛma aba. Bankye nkotokuo so akyene borɔ aba.",
        "level": "medium",
        "tip": "Remove infected leaves. Improve airflow by spacing plants well.",
        "tip_tw": "Yi nkotokuo a yareɛ wɔ so no.",
    },
    {
        "name": "Aphids",              "name_tw": "Mmoa Ketewa",
        "crops": "Vegetables",         "crops_tw": "Atosɔde",
        "description": "Low pressure this week. Monitor undersides of leaves.",
        "description_tw": "Ɔhaw ketewa. Hwɛ nkotokuo ase.",
        "level": "low",
        "tip": "Spray with diluted soapy water or introduce ladybird beetles.",
        "tip_tw": "De nsuo ne sapo mu ngu so.",
    },
    {
        "name": "Cassava Mosaic Virus","name_tw": "Bankye Yareɛ Kɛseɛ",
        "crops": "Cassava",            "crops_tw": "Bankye",
        "description": "Spread by whiteflies. Yellowing and distortion of leaves.",
        "description_tw": "Nsansanwa na ɛde ba. Nkotokuo sere na wɔsɛe.",
        "level": "medium",
        "tip": "Use certified disease-free planting material. Control whitefly populations.",
        "tip_tw": "Fa bankye a yareɛ nni so.",
    },
]

QUICK_QUESTIONS_EN = [
    "What crop should I plant in Ghana during the minor rainy season?",
    "How do I treat Fall Armyworm on my maize crop with local methods?",
    "When is the best time to sell my tomatoes to get the best price?",
    "How do I know if my soil is ready for planting?",
    "What fertilizer should I use for maize farming in Ghana?",
    "How can I store my harvest longer without refrigeration?",
]

QUICK_QUESTIONS_TW = [
    "Aba bɛn na mɛdua wɔ Ghana wɔ osu ketewa ɔberɛ?",
    "Ɛdeɛn na mɛyɛ aburo mmoa ho wɔ me aburo afuo so?",
    "Ɛberɛ bɛn na ɛsɛ sɛ metɔn me ntomato na menya wuramu pa?",
    "Ɛdeɛn na mɛhunu sɛ me asaase atoto adua?",
    "Aduro bɛn na mɛfa ama aburo adwuma wɔ Ghana?",
    "Ɛdeɛn na mɛtumi de me aba sie akɔ akyiri sen saa?",
]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(
        "index.html",
        weather=get_weather("greater_accra"),
        prices=PRICE_DATA,
        pests=PEST_DATA,
        quick_questions_en=QUICK_QUESTIONS_EN,
        quick_questions_tw=QUICK_QUESTIONS_TW,
        regions=GHANA_REGIONS,
        api_ready=bool(client.api_key),
    )

@app.route("/api/weather")
def api_weather():
    region_key = request.args.get("region", "greater_accra")
    if region_key not in GHANA_REGIONS:
        region_key = "greater_accra"
    return jsonify(get_weather(region_key))

@app.route("/api/prices")
def api_prices():
    return jsonify(PRICE_DATA)

@app.route("/api/pests")
def api_pests():
    return jsonify(PEST_DATA)

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    if not client.api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set."}), 500

    data       = request.get_json()
    image_b64  = data.get("image")
    media_type = data.get("media_type", "image/jpeg")
    lang       = data.get("lang", "en")

    if not image_b64:
        return jsonify({"error": "No image provided"}), 400

    prompt = DISEASE_PROMPT_TW if lang == "tw" else DISEASE_PROMPT_EN

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text",  "text": prompt},
                ],
            }],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data     = request.get_json()
    messages = data.get("messages", [])
    lang     = data.get("lang", "en")

    if not messages:
        return jsonify({"error": "No messages provided"}), 400
    if not client.api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set."}), 500

    system = SYSTEM_PROMPT_TW if lang == "tw" else SYSTEM_PROMPT_EN

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n🌿 FarmWise AI starting...")
    print("   API key set:", bool(client.api_key))
    print("   Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)

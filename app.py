"""
FarmWise AI - Farmer Assistant Tool
Powered by Anthropic Claude API + Open-Meteo (live weather)
Features: Live weather, AI chat, Photo disease diagnosis, Twi language support

Run:
    pip install flask anthropic requests gunicorn
    export ANTHROPIC_API_KEY=sk-ant-your-key-here
    python app.py

Then open: http://localhost:5000
"""

import os
import json
import base64
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
wɔ Ghana ne Atɔeɛ Afrika mu. Woboa wɔn ho asɛm a ɛfa:

1. ƆHAW NE NSUO HOHOROW - kyerɛ osu ho asɛm, ka wɔn ho asɛm faako wɔn hwehwɛ nsuo, 
   ɛberɛ a ɛsɛ sɛ wɔdua aba, ne ɔhaw a osu bɛma wɔn afuo mu aba.
2. AGUADI TENTEENE - ka wɔn ho asɛm faako wɔn tɔ adwuma ho gɔdo, ɛberɛ a ɛsɛ sɛ wɔtɔn 
   wɔn aba, ne wuramu tenteene a ɛfa bɔrɔdeɛ, bankye, ntomato, ɔgede, bayerɛ, kookoo, 
   ne nnuaba foforo a wɔdua wɔ Ghana.
3. MMOA YAREƐ NHYEHYƐE - kyerɛ nsɛnkyerɛnne, ka wɔn ho asɛm faako aduro a wɔbɛtumi 
   de ayɛ, ne mmara a ɛbɛboa wɔn fi mmoa tia wɔn afuo ho.
4. DUA ABA NHYEHYƐE - afuo aba bɛn na ɛfata ɔberɛ no, asaase no, ne osu no.

Fa asɛm a ɛho hia, a wɔbɛtumi ayɛ, na ɛka nnomkuo nkuraasefoɔ afuom adwumayɛfoɔ ho.
Ka asɛm no ntɛm, dwoodwoo, na sɔ wɔn da. Fa kasa a ɛyɛ mmerɛw. Sɛ asɛm no ho hia a, 
fa afuo aba din a wɔde frɛ wɔn wɔ Ghana ne aguadi baabi (Kumasi, Accra, Tamale).
"""

DISEASE_PROMPT_EN = """You are an expert plant pathologist for Ghana and West Africa crops.
Analyze this crop photo and provide:

1. DISEASE/PEST NAME - what you see affecting the crop
2. CROP AFFECTED - identify the crop if visible
3. SEVERITY - Low / Medium / High
4. SYMPTOMS - what visible signs you can see in the image
5. TREATMENT - affordable, practical treatment steps available to smallholder farmers in Ghana
6. PREVENTION - how to prevent this in future

Be specific, practical, and mention locally available products where possible.
If the image is not a crop or plant, politely say so and ask for a crop photo.
Format your response clearly with these headings.
"""

DISEASE_PROMPT_TW = """Wo yɛ ogya a ɔnim aba yareɛ wɔ Ghana ne Atɔeɛ Afrika afuo mu.
Hwɛ saa afuo foto yi na ka:

1. YAREƐ/MMOA DIN - deɛ wohunu a ɛreyɛ aba no yaw
2. ABA A ƐWƆ SO - hunu aba no sɛ wohunu no
3. YAREƐ TENTEN - Ketewa / Mfinimfini / Kɛseɛ
4. NSƐNKYERƐNNE - nsɛnkyerɛnne a wohunu wɔ foto no mu
5. ADURO - aduro a ɛyɛ mmerɛw na ɛho hia a nnomkuo afuom adwumayɛfoɔ wɔ Ghana bɛtumi de ayɛ
6. BANBƆ - ɛdeɛn na wɔbɛtumi ayɛ sɛ eyi ammɛba bio

Yɛ pɛpɛɛpɛ, na ka aduro a wɔtumi nya wɔ Ghana. Sɛ foto no nyɛ aba anaa nnua a, 
ka no dɔɔso na bisa wɔn afuo foto.
"""

# ---------------------------------------------------------------------------
# Live weather from Open-Meteo
# ---------------------------------------------------------------------------
def get_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=5.55&longitude=-0.20"
            "&daily=temperature_2m_max,precipitation_probability_max,windspeed_10m_max"
            "&hourly=relativehumidity_2m"
            "&forecast_days=7"
            "&timezone=Africa%2FAccra"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        daily = data["daily"]
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
            advice     = "Heavy rain expected. Avoid spraying pesticides today. Check field drainage."
            advice_tw  = "Osu kɛseɛ reba. Mma aduro gu afuo so nnɛ. Hwɛ sɛ nsuo bɛtumi afi afuo no mu."
            risk       = "High flood / waterlogging risk"
            risk_tw    = "Osu kɛseɛ tumi de ɔhaw ba"
            risk_level = "danger"
        elif today_rain >= 40:
            advice     = "Moderate rain likely. Skip irrigation on rainy days to conserve water."
            advice_tw  = "Osu kakra reba. Mma nsuo gu afuo so da a osu ba no."
            risk       = "Moderate moisture stress risk"
            risk_tw    = "Nsuo haw mfinimfini"
            risk_level = "warn"
        else:
            advice     = "Dry conditions ahead. Irrigate crops well, especially young seedlings."
            advice_tw  = "Awia bɛyɛ den. Ma nsuo gu wo aba so, titiriw mma nketewa no."
            risk       = "Low rainfall — monitor soil moisture"
            risk_tw    = "Osu ketewa — hwɛ asaase nsuo"
            risk_level = "ok"

        return {
            "location":    "Accra Region, Ghana",
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

    except Exception as e:
        print(f"[Weather API error] {e}")
        return {
            "location":    "Accra Region, Ghana",
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
            "advice":      "Weather data temporarily unavailable.",
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
    {"crop": "Maize",     "crop_tw": "Aburo",      "unit": "50kg bag",   "price": 240, "change": 8,   "trend": "up"},
    {"crop": "Tomatoes",  "crop_tw": "Ntomato",    "unit": "crate",      "price": 180, "change": -12, "trend": "down"},
    {"crop": "Cassava",   "crop_tw": "Bankye",     "unit": "100kg bag",  "price": 310, "change": 0,   "trend": "stable"},
    {"crop": "Plantain",  "crop_tw": "Ɔgede",      "unit": "bunch",      "price": 55,  "change": 3,   "trend": "up"},
    {"crop": "Yam",       "crop_tw": "Bayerɛ",     "unit": "tuber (lg)", "price": 35,  "change": 5,   "trend": "up"},
    {"crop": "Cocoa",     "crop_tw": "Kookoo",     "unit": "kg dry bean","price": 24,  "change": 2,   "trend": "up"},
    {"crop": "Pepper",    "crop_tw": "Mako",       "unit": "kg",         "price": 28,  "change": -5,  "trend": "down"},
    {"crop": "Groundnut", "crop_tw": "Nkatie",     "unit": "50kg bag",   "price": 290, "change": 1,   "trend": "stable"},
]

PEST_DATA = [
    {
        "name": "Fall Armyworm", "name_tw": "Aburo Mmoa",
        "crops": "Maize", "crops_tw": "Aburo",
        "description": "High risk season. Check leaves for feeding damage and egg masses.",
        "description_tw": "Ɔberɛ kɛseɛ. Hwɛ nkotokuo so sɛ mmoa adidi so anaa wɔada ɛfa so.",
        "level": "high",
        "tip": "Apply neem-based spray early morning. Report sightings to extension officer.",
        "tip_tw": "De neem aduro gu so anɔpa. Ka kyerɛ wo agyinafoɔ sɛ wohunu no.",
    },
    {
        "name": "Cassava Leaf Blight", "name_tw": "Bankye Nkotokuo Yareɛ",
        "crops": "Cassava", "crops_tw": "Bankye",
        "description": "Humidity-driven fungal disease. Angular brown spots on leaves.",
        "description_tw": "Yareɛ a nsuo ɛma aba. Bankye nkotokuo so akyene borɔ aba.",
        "level": "medium",
        "tip": "Remove infected leaves. Improve airflow by spacing plants well.",
        "tip_tw": "Yi nkotokuo a yareɛ wɔ so no. Ma mframa ntumi tra mu yie.",
    },
    {
        "name": "Aphids", "name_tw": "Mmoa Ketewa",
        "crops": "Vegetables", "crops_tw": "Atosɔde",
        "description": "Low pressure this week. Monitor undersides of leaves.",
        "description_tw": "Ɔhaw ketewa wiemuhyɛn yi. Hwɛ nkotokuo ase.",
        "level": "low",
        "tip": "Spray with diluted soapy water or introduce ladybird beetles.",
        "tip_tw": "De nsuo ne sapo mu ngu so anaa fa beetles a ɛdi wɔn.",
    },
    {
        "name": "Cassava Mosaic Virus", "name_tw": "Bankye Yareɛ Kɛseɛ",
        "crops": "Cassava", "crops_tw": "Bankye",
        "description": "Spread by whiteflies. Yellowing and distortion of leaves.",
        "description_tw": "Nsansanwa na ɛde ba. Nkotokuo sere na wɔsɛe.",
        "level": "medium",
        "tip": "Use certified disease-free planting material. Control whitefly populations.",
        "tip_tw": "Fa bankye a yareɛ nni so. Tia nsansanwa a ɛwɔ hɔ.",
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
        weather=get_weather(),
        prices=PRICE_DATA,
        pests=PEST_DATA,
        quick_questions_en=QUICK_QUESTIONS_EN,
        quick_questions_tw=QUICK_QUESTIONS_TW,
        api_ready=bool(client.api_key),
    )

@app.route("/api/weather")
def api_weather():
    return jsonify(get_weather())

@app.route("/api/prices")
def api_prices():
    return jsonify(PRICE_DATA)

@app.route("/api/pests")
def api_pests():
    return jsonify(PEST_DATA)


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """Analyse a crop photo for disease using Claude Vision."""
    if not client.api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set."}), 500

    data     = request.get_json()
    image_b64 = data.get("image")
    media_type = data.get("media_type", "image/jpeg")
    lang     = data.get("lang", "en")

    if not image_b64:
        return jsonify({"error": "No image provided"}), 400

    prompt = DISEASE_PROMPT_TW if lang == "tw" else DISEASE_PROMPT_EN

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Streaming chat powered by Claude."""
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


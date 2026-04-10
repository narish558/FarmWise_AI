"""
FarmWise AI - Farmer Assistant Tool
Powered by Anthropic Claude API + Open-Meteo (live weather)

Run:
    pip install flask anthropic requests gunicorn
    export ANTHROPIC_API_KEY=sk-ant-your-key-here
    python app.py

Then open: http://localhost:5000
"""

import os
import json
import requests
import anthropic
from flask import Flask, render_template, request, jsonify, stream_with_context, Response

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Anthropic client (reads ANTHROPIC_API_KEY from environment)
# ---------------------------------------------------------------------------
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

SYSTEM_PROMPT = """You are FarmWise AI, a knowledgeable and friendly farming assistant focused on 
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

# ---------------------------------------------------------------------------
# Live weather from Open-Meteo (free, no API key needed)
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
            if pct < 30:
                return "☀️"
            elif pct < 60:
                return "⛅"
            else:
                return "🌧️"

        forecast = [
            {
                "day": day_names[i % 7],
                "icon": rain_icon(daily["precipitation_probability_max"][i]),
                "high": round(daily["temperature_2m_max"][i]),
                "rain": daily["precipitation_probability_max"][i],
            }
            for i in range(min(7, len(daily["temperature_2m_max"])))
        ]

        today_rain  = daily["precipitation_probability_max"][0]
        today_high  = round(daily["temperature_2m_max"][0])
        today_wind  = round(daily["windspeed_10m_max"][0])
        humidity    = data["hourly"]["relativehumidity_2m"][12]

        if today_rain >= 70:
            advice     = "Heavy rain expected. Avoid spraying pesticides today. Check field drainage to prevent waterlogging and root rot."
            risk       = "High flood / waterlogging risk"
            risk_level = "danger"
        elif today_rain >= 40:
            advice     = "Moderate rain likely this week. Skip irrigation on rainy days to conserve water and reduce fungal disease risk."
            risk       = "Moderate moisture stress risk"
            risk_level = "warn"
        else:
            advice     = "Dry conditions ahead. Ensure crops are adequately irrigated, especially young seedlings. Good time for field operations."
            risk       = "Low rainfall — monitor soil moisture closely"
            risk_level = "ok"

        return {
            "location":    "Accra Region, Ghana",
            "today_high":  today_high,
            "humidity":    humidity,
            "rain_chance": today_rain,
            "wind_kmh":    today_wind,
            "forecast":    forecast,
            "advice":      advice,
            "risk":        risk,
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
            "advice":      "Weather data temporarily unavailable. Please check back shortly.",
            "risk":        "Data unavailable",
            "risk_level":  "warn",
            "live":        False,
        }


# ---------------------------------------------------------------------------
# Market prices (update manually each week from MoFA / Kumasi market)
# ---------------------------------------------------------------------------
PRICE_DATA = [
    {"crop": "Maize",     "unit": "50kg bag",   "price": 240, "change": 8,   "trend": "up"},
    {"crop": "Tomatoes",  "unit": "crate",       "price": 180, "change": -12, "trend": "down"},
    {"crop": "Cassava",   "unit": "100kg bag",   "price": 310, "change": 0,   "trend": "stable"},
    {"crop": "Plantain",  "unit": "bunch",       "price": 55,  "change": 3,   "trend": "up"},
    {"crop": "Yam",       "unit": "tuber (lg)",  "price": 35,  "change": 5,   "trend": "up"},
    {"crop": "Cocoa",     "unit": "kg dry bean", "price": 24,  "change": 2,   "trend": "up"},
    {"crop": "Pepper",    "unit": "kg",          "price": 28,  "change": -5,  "trend": "down"},
    {"crop": "Groundnut", "unit": "50kg bag",    "price": 290, "change": 1,   "trend": "stable"},
]

# ---------------------------------------------------------------------------
# Pest alerts
# ---------------------------------------------------------------------------
PEST_DATA = [
    {
        "name":        "Fall Armyworm",
        "crops":       "Maize",
        "description": "High risk season. Check leaves for feeding damage and egg masses.",
        "level":       "high",
        "tip":         "Apply neem-based spray early morning. Report sightings to extension officer.",
    },
    {
        "name":        "Cassava Leaf Blight",
        "crops":       "Cassava",
        "description": "Humidity-driven fungal disease. Angular brown spots on leaves.",
        "level":       "medium",
        "tip":         "Remove infected leaves. Improve airflow by spacing plants well.",
    },
    {
        "name":        "Aphids",
        "crops":       "Vegetables",
        "description": "Low pressure this week. Monitor undersides of leaves.",
        "level":       "low",
        "tip":         "Spray with diluted soapy water or introduce ladybird beetles.",
    },
    {
        "name":        "Cassava Mosaic Virus",
        "crops":       "Cassava",
        "description": "Spread by whiteflies. Yellowing and distortion of leaves.",
        "level":       "medium",
        "tip":         "Use certified disease-free planting material. Control whitefly populations.",
    },
]

# ---------------------------------------------------------------------------
# Quick questions
# ---------------------------------------------------------------------------
QUICK_QUESTIONS = [
    "What crop should I plant in Ghana during the minor rainy season?",
    "How do I treat Fall Armyworm on my maize crop with local methods?",
    "When is the best time to sell my tomatoes to get the best price?",
    "How do I know if my soil is ready for planting?",
    "What fertilizer should I use for maize farming in Ghana?",
    "How can I store my harvest longer without refrigeration?",
]

# ---------------------------------------------------------------------------
# Admin route to update prices without redeploying
# ---------------------------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "farmwise2024")

@app.route("/admin/prices", methods=["POST"])
def admin_update_prices():
    data = request.get_json()
    if not data or data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 403
    global PRICE_DATA
    PRICE_DATA = data["prices"]
    return jsonify({"success": True, "updated": len(PRICE_DATA)})


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
        quick_questions=QUICK_QUESTIONS,
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

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "No messages provided"}), 400
    if not client.api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set."}), 500

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
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

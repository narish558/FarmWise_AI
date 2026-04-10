"""
FarmWise AI - Farmer Assistant Tool
Powered by Anthropic Claude API

Run:
    pip install flask anthropic requests
    python app.py
Then open: http://localhost:5000
"""

import os
import json
import anthropic
from flask import Flask, render_template, request, jsonify, stream_with_context, Response

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Anthropic client  (reads ANTHROPIC_API_KEY from environment)
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
(e.g. "obroni wawu" maize varieties, etc.) and local markets (Kumasi, Accra, Tamale).
If a question is outside farming, gently redirect back to farming topics.
"""

# ---------------------------------------------------------------------------
# Static data (in production, replace with live API calls)
# ---------------------------------------------------------------------------
WEATHER_DATA = {
    "location": "Accra Region, Ghana",
    "today_high": 34,
    "humidity": 78,
    "rain_chance": 60,
    "wind_kmh": 14,
    "forecast": [
        {"day": "Mon", "icon": "☀️", "high": 34, "rain": 10},
        {"day": "Tue", "icon": "⛅", "high": 33, "rain": 30},
        {"day": "Wed", "icon": "🌧️", "high": 29, "rain": 75},
        {"day": "Thu", "icon": "🌧️", "high": 28, "rain": 80},
        {"day": "Fri", "icon": "⛅", "high": 31, "rain": 40},
        {"day": "Sat", "icon": "☀️", "high": 33, "rain": 15},
        {"day": "Sun", "icon": "☀️", "high": 34, "rain": 10},
    ],
    "advice": "Rain expected mid-week. Skip irrigation Wednesday–Thursday. Watch for fungal disease due to high humidity.",
    "risk": "Moderate moisture stress risk",
    "risk_level": "warn",
}

PRICE_DATA = [
    {"crop": "Maize",    "unit": "50kg bag",   "price": 240, "change": +8,  "trend": "up"},
    {"crop": "Tomatoes", "unit": "crate",       "price": 180, "change": -12, "trend": "down"},
    {"crop": "Cassava",  "unit": "100kg bag",   "price": 310, "change": 0,   "trend": "stable"},
    {"crop": "Plantain", "unit": "bunch",        "price": 55,  "change": +3,  "trend": "up"},
    {"crop": "Yam",      "unit": "tuber (lg)",  "price": 35,  "change": +5,  "trend": "up"},
    {"crop": "Cocoa",    "unit": "kg dry bean", "price": 24,  "change": +2,  "trend": "up"},
    {"crop": "Pepper",   "unit": "kg",           "price": 28,  "change": -5,  "trend": "down"},
    {"crop": "Groundnut","unit": "50kg bag",     "price": 290, "change": +1,  "trend": "stable"},
]

PEST_DATA = [
    {
        "name": "Fall Armyworm",
        "crops": "Maize",
        "description": "High risk season. Check leaves for feeding damage and egg masses.",
        "level": "high",
        "tip": "Apply neem-based spray early morning. Report sightings to extension officer.",
    },
    {
        "name": "Cassava Leaf Blight",
        "crops": "Cassava",
        "description": "Humidity-driven fungal disease. Angular brown spots on leaves.",
        "level": "medium",
        "tip": "Remove infected leaves. Improve airflow by spacing plants well.",
    },
    {
        "name": "Aphids",
        "crops": "Vegetables",
        "description": "Low pressure this week. Monitor undersides of leaves.",
        "level": "low",
        "tip": "Spray with diluted soapy water or introduce ladybird beetles.",
    },
    {
        "name": "Cassava Mosaic Virus",
        "crops": "Cassava",
        "description": "Spread by whiteflies. Yellowing and distortion of leaves.",
        "level": "medium",
        "tip": "Use certified disease-free planting material. Control whitefly populations.",
    },
]

QUICK_QUESTIONS = [
    "What crop should I plant in Ghana during the minor rainy season?",
    "How do I treat Fall Armyworm on my maize crop with local methods?",
    "When is the best time to sell my tomatoes to get the best price?",
    "How do I know if my soil is ready for planting?",
    "What fertilizer should I use for maize farming in Ghana?",
    "How can I store my harvest longer without refrigeration?",
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        weather=WEATHER_DATA,
        prices=PRICE_DATA,
        pests=PEST_DATA,
        quick_questions=QUICK_QUESTIONS,
        api_ready=bool(client.api_key),
    )


@app.route("/api/weather")
def api_weather():
    return jsonify(WEATHER_DATA)


@app.route("/api/prices")
def api_prices():
    return jsonify(PRICE_DATA)


@app.route("/api/pests")
def api_pests():
    return jsonify(PEST_DATA)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Streaming chat endpoint powered by Claude."""
    data = request.get_json()
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "No messages provided"}), 400

    if not client.api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set. Please set the environment variable."}), 500

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


if __name__ == "__main__":
    print("\n🌿 FarmWise AI is starting...")
    print("   Set your API key: export ANTHROPIC_API_KEY=your_key_here")
    print("   Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)

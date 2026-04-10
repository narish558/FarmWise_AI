# 🌿 FarmWise AI

An AI-powered farming assistant for smallholder farmers in Ghana and West Africa.  
Built with **Python**, **Flask**, and **Anthropic Claude**.

## Features

| Tab | What it does |
|-----|-------------|
| 🌤 Weather | 7-day forecast + irrigation advice |
| 📈 Prices | Live market prices for 8 common crops |
| 🐛 Pests | Pest alerts with risk levels + treatment tips |
| 🤖 Ask AI | Streaming chat powered by Claude |

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key
```bash
# Mac / Linux
export ANTHROPIC_API_KEY=sk-ant-...

# Windows
set ANTHROPIC_API_KEY=sk-ant-...
```

Get a free API key at: https://console.anthropic.com

### 3. Run the app
```bash
python app.py
```

### 4. Open in browser
```
http://localhost:5000
```

---

## Project Structure

```
farmwise/
├── app.py                  # Flask app + Claude API integration
├── requirements.txt        # Python dependencies
├── README.md
└── templates/
    └── index.html          # Single-page UI
```

## Extending the App

### Add live weather data
Replace `WEATHER_DATA` in `app.py` with a call to [Open-Meteo](https://open-meteo.com/) (free, no key needed):
```python
import requests
r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=5.55&longitude=-0.20&daily=temperature_2m_max,precipitation_probability_max&forecast_days=7")
data = r.json()
```

### Add live market prices
Connect to Ghana's MoFA price database or scrape local market boards.

### Deploy to production
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

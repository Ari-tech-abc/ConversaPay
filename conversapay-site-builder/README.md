# 🚀 ConversaPay Site Builder

AI-powered website builder that generates beautiful, responsive landing pages using Google's Gemini API.

## ✨ Features

- **AI-Powered Generation**: Describe your business and get a complete landing page in seconds
- **JSON-to-UI Pattern**: Reliable, structured output using validated JSON configurations
- **Multiple Design Vibes**: Choose from Minimalist, Cyber, Luxury, or Playful styles
- **Live Preview**: See your generated site in real-time with desktop/mobile toggle
- **Production-Ready**: Generates semantic HTML with Tailwind CSS
- **Multi-Tenant Ready**: Built with scalability in mind

## 🏗️ Architecture

```
conversapay-site-builder/
├── backend/
│   ├── __init__.py
│   ├── config.py           # Configuration settings
│   ├── main.py             # FastAPI app with CORS
│   └── routers/
│       ├── __init__.py
│       └── generator.py    # AI generation endpoint
├── frontend/
│   └── index.html          # Site builder wizard UI
├── requirements.txt        # Python dependencies
└── README.md
```

## 🔧 Installation

### Prerequisites

- Python 3.9+
- Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd conversapay-site-builder
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your Gemini API key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

5. **Run the server**
   ```bash
   python -m backend.main
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
   ```

6. **Access the application**
   - Frontend: Open `frontend/index.html` in your browser
   - API Docs: http://localhost:8001/docs
   - Health Check: http://localhost:8001/health

## 📡 API Endpoints

### POST /api/v1/builder/generate

Generate a complete website configuration using AI.

**Request Body:**
```json
{
  "prompt": "A modern sushi restaurant in Tokyo with dark-mode vibes",
  "business_name": "Sushi Master Tokyo",
  "industry": "restaurant",
  "vibe": "minimalist",
  "sections": ["hero", "features", "testimonials"]
}
```

**Response:**
```json
{
  "success": true,
  "config": {
    "hero": {
      "headline": "Authentic Japanese Cuisine",
      "subheadline": "Experience the finest sushi in Tokyo",
      "primaryCTA": {
        "text": "Reserve a Table",
        "link": "#",
        "style": "primary"
      }
    },
    "features": [...],
    "theme": {
      "primaryColor": "#3B82F6",
      "backgroundColor": "#FFFFFF",
      "fontStack": "Inter"
    }
  },
  "html": "<!DOCTYPE html>..."
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "conversapay-site-builder",
  "ai_enabled": true
}
```

## 🎨 Design Vibes

- **Minimalist Light**: Clean, lots of whitespace, simple colors, elegant typography
- **Cyber Dark**: Dark mode, neon accents, futuristic feel, gradients
- **Luxury Gold**: Gold accents, elegant fonts, premium feel, sophisticated colors
- **Playful**: Bright colors, fun icons, energetic feel, rounded elements

## 🔒 Security

- CORS configured for specific origins
- Input validation with Pydantic models
- Rate limiting ready (configure in production)
- No sensitive data exposure

## 🚀 Deployment

### Using Docker (Recommended)

```dockerfile
# Dockerfile example
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `DEBUG` | Enable debug mode | No |
| `HOST` | Server host | No (default: 0.0.0.0) |
| `PORT` | Server port | No (default: 8001) |

## 📝 License

Proprietary - ConversaPay

## 👥 Contributing

This is an internal ConversaPay project. For questions or support, contact the development team.

## 🔗 Related Projects

- [ConversaPay Main App](https://github.com/Ari-tech-abc/ConversaPay.proj.git)
- [ConversaPay Documentation](https://conversapay.org/docs)

---

Built with ❤️ by ConversaPay Team
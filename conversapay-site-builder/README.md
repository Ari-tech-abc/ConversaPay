# 🚀 Talk2Pay Site Builder

AI-powered website builder that generates beautiful, responsive landing pages using Google's Gemini API.

## ✨ Features

- **AI-Powered Generation**: Describe your business and get a complete landing page in seconds
- **JSON-to-UI Pattern**: Reliable, structured output using validated JSON configurations
- **Multiple Design Vibes**: Choose from Minimalist, Cyber, Luxury, or Playful styles
- **Live Preview**: See your generated site in real-time with desktop/mobile toggle
- **Production-Ready**: Generates semantic HTML with responsive markup
- **Multi-Tenant Ready**: Built with scalability in mind

## 🏗️ Architecture

The builder is served as part of the Talk2Pay product. The directory name and domain paths retain `conversapay` for compatibility with existing deployments and clients.

```
conversapay-site-builder/
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   └── routers/
├── frontend/
│   └── index.html
├── requirements.txt
└── README.md
```

## 🔧 Installation

### Prerequisites

- Python 3.9+
- Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

### Setup

1. Clone the repository.
2. Create a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and add the Gemini key.
5. Run `python -m backend.main`.

## 📡 API Endpoints

### POST /api/v1/builder/generate

Generate a complete website configuration using AI. Input is validated and generated HTML is escaped and rendered with semantic responsive markup.

### GET /health

Returns the builder health status.

## 🔒 Security

- CORS is restricted to configured origins.
- Input validation is enforced with Pydantic models.
- Generated content is escaped before rendering.
- Sensitive credentials are never sent to generated client code.

## 🚀 Deployment

The main Talk2Pay service owns the production deployment. Keep `conversapay.org` and technical compatibility identifiers unchanged until a documented migration is complete.

## 📝 License

Proprietary, Talk2Pay.

## 🔗 Related Projects

- Talk2Pay Main App: the root repository
- Talk2Pay Documentation: https://conversapay.org/docs

---

Built with ❤️ by the Talk2Pay Team

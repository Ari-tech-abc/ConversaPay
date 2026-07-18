"""
AI Website Builder Router
Generates beautiful, responsive landing pages using Gemini AI.
Uses JSON-to-UI pattern for reliable, structured output.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import google.generativeai as genai
import json
import re

from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["website-builder"])

# Configure Gemini AI
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None
    logger.warning("GEMINI_API_KEY not configured - AI generation disabled")


# ============================================
# Pydantic Models
# ============================================

class CTAModel(BaseModel):
    """Call-to-action button model."""
    text: str
    link: str
    style: str = "primary"  # primary, secondary, outline


class HeroSection(BaseModel):
    """Hero section configuration."""
    headline: str
    subheadline: str
    primaryCTA: CTAModel
    secondaryCTA: Optional[CTAModel] = None
    layoutStyle: str = "centered"  # centered, split, minimal
    backgroundImage: Optional[str] = None
    badge: Optional[str] = None


class FeatureItem(BaseModel):
    """Feature item model."""
    title: str
    description: str
    iconStyle: str = "default"  # default, gradient, outlined
    link: Optional[str] = None


class ProductItem(BaseModel):
    """Product/service item model."""
    title: str
    pricePlaceholder: str
    description: str
    imageUrl: Optional[str] = None
    features: List[str] = []


class TestimonialItem(BaseModel):
    """Testimonial item model."""
    quote: str
    author: str
    role: str
    avatarUrl: Optional[str] = None


class ThemeConfig(BaseModel):
    """Theme configuration model."""
    primaryColor: str = "#3B82F6"
    backgroundColor: str = "#FFFFFF"
    fontStack: str = "Inter"
    textColor: str = "#1F2937"
    secondaryColor: str = "#6B7280"
    borderRadius: str = "8px"
    spacing: str = "comfortable"  # compact, comfortable, spacious


class SiteConfig(BaseModel):
    """Complete site configuration."""
    hero: HeroSection
    features: List[FeatureItem]
    products: Optional[List[ProductItem]] = None
    testimonials: Optional[List[TestimonialItem]] = None
    theme: ThemeConfig
    seo: Optional[Dict[str, str]] = None


class GenerateRequest(BaseModel):
    """Request model for site generation."""
    prompt: str = Field(..., min_length=10, max_length=1000, description="Business description")
    business_name: str = Field(..., min_length=2, max_length=100)
    industry: str = Field(..., min_length=2, max_length=50)
    vibe: str = Field(default="modern", description="Design vibe: minimalist, cyber, luxury, playful")
    sections: List[str] = Field(default=["hero", "features", "testimonials"])


class GenerateResponse(BaseModel):
    """Response model for generated site."""
    success: bool
    config: Optional[SiteConfig] = None
    html: Optional[str] = None
    error: Optional[str] = None


# ============================================
# AI Generation Logic
# ============================================

def build_system_prompt() -> str:
    """Build system prompt for Gemini AI."""
    return """You are an expert web designer and developer specializing in creating beautiful, modern, production-ready landing pages.

Your task is to generate a JSON configuration object for a stunning website based on the user's business description.

CRITICAL RULES:
1. Output ONLY valid JSON - no markdown, no explanations, no code blocks
2. Follow the exact schema structure provided below
3. Use beautiful spacing (py-20, py-24, py-32 for sections)
4. Use strict grid alignments and modern design principles
5. Ensure all text is in the same language as the user's prompt
6. Make it premium, professional, and conversion-focused

SCHEMA STRUCTURE:
{
  "hero": {
    "headline": "string (max 60 chars)",
    "subheadline": "string (max 120 chars)",
    "primaryCTA": {
      "text": "string",
      "link": "#",
      "style": "primary"
    },
    "secondaryCTA": {
      "text": "string (optional)",
      "link": "#",
      "style": "outline"
    },
    "layoutStyle": "centered",
    "badge": "string (optional)"
  },
  "features": [
    {
      "title": "string",
      "description": "string (max 100 chars)",
      "iconStyle": "default"
    }
  ],
  "products": [
    {
      "title": "string",
      "pricePlaceholder": "string (e.g., '$99/month')",
      "description": "string",
      "features": ["feature1", "feature2", "feature3"]
    }
  ],
  "testimonials": [
    {
      "quote": "string (max 200 chars)",
      "author": "string",
      "role": "string"
    }
  ],
  "theme": {
    "primaryColor": "#hex",
    "backgroundColor": "#hex",
    "fontStack": "Inter",
    "textColor": "#hex",
    "secondaryColor": "#hex",
    "borderRadius": "8px",
    "spacing": "comfortable"
  },
  "seo": {
    "title": "string",
    "description": "string"
  }
}

DESIGN PRINCIPLES:
- Use generous padding: py-20, py-24, py-32 for sections
- Use modern typography with clear hierarchy
- Use subtle shadows and rounded corners
- Ensure excellent contrast and readability
- Make CTAs prominent and action-oriented
- Use professional, benefit-focused copy
- Include social proof elements (testimonials, stats)
- Make it mobile-responsive by default

VIBE ADAPTATIONS:
- minimalist: Clean, lots of whitespace, simple colors, elegant typography
- cyber: Dark mode, neon accents, futuristic feel, gradients
- luxury: Gold accents, elegant fonts, premium feel, sophisticated colors
- playful: Bright colors, fun icons, energetic feel, rounded elements

Generate the JSON now based on the user's request. Remember: ONLY JSON, no other text."""


def clean_json_response(text: str) -> str:
    """Clean and extract JSON from AI response."""
    # Remove markdown code blocks if present
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    
    # Find JSON object
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json_match.group(0)
    
    return text.strip()


@router.post("/generate", response_model=GenerateResponse)
async def generate_site(request: GenerateRequest):
    """
    Generate a complete website configuration using AI.
    
    Takes a business description and returns a structured JSON configuration
    that can be rendered into a beautiful landing page.
    """
    try:
        if not model:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service not configured. Please set GEMINI_API_KEY."
            )
        
        logger.info(f"Generating site for: {request.business_name} ({request.industry})")
        
        # Build the prompt
        user_prompt = f"""
Business Name: {request.business_name}
Industry: {request.industry}
Design Vibe: {request.vibe}
Description: {request.prompt}

Sections to include: {', '.join(request.sections)}

Generate a beautiful, modern landing page configuration for this business.
"""
        
        # Call Gemini AI
        response = model.generate_content(
            f"{build_system_prompt()}\n\n{user_prompt}",
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 2048,
            }
        )
        
        # Extract and clean JSON
        json_text = clean_json_response(response.text)
        
        # Parse JSON
        try:
            config_dict = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from AI: {json_text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI generated invalid configuration: {str(e)}"
            )
        
        # Validate with Pydantic
        try:
            site_config = SiteConfig(**config_dict)
        except Exception as e:
            logger.error(f"Configuration validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid configuration structure: {str(e)}"
            )
        
        # Generate HTML from config
        html = generate_html_from_config(site_config)
        
        logger.info(f"Successfully generated site for: {request.business_name}")
        
        return GenerateResponse(
            success=True,
            config=site_config,
            html=html
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Site generation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate site: {str(e)}"
        )


def generate_html_from_config(config: SiteConfig) -> str:
    """
    Generate HTML from site configuration.
    Creates a beautiful, responsive landing page.
    """
    theme = config.theme
    
    html = f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{config.seo.get('title', 'Generated Site') if config.seo else 'Generated Site'}</title>
    <meta name="description" content="{config.seo.get('description', '') if config.seo else ''}">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family={theme.fontStack.replace(' ', '+')}:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        primary: '{theme.primaryColor}',
                        secondary: '{theme.secondaryColor}',
                    }},
                    fontFamily: {{
                        sans: ['{theme.fontStack}', 'sans-serif'],
                    }},
                }}
            }}
        }}
    </script>
    <style>
        body {{
            font-family: '{theme.fontStack}', sans-serif;
            background-color: {theme.backgroundColor};
            color: {theme.textColor};
        }}
    </style>
</head>
<body>
    <!-- Hero Section -->
    <section class="py-24 px-4" style="background-color: {theme.backgroundColor};">
        <div class="max-w-7xl mx-auto text-center">
            {f'<span class="inline-block px-4 py-2 rounded-full text-sm font-semibold mb-6" style="background-color: {theme.primaryColor}20; color: {theme.primaryColor};">{config.hero.badge}</span>' if config.hero.badge else ''}
            <h1 class="text-5xl md:text-7xl font-bold mb-6" style="color: {theme.textColor};">
                {config.hero.headline}
            </h1>
            <p class="text-xl md:text-2xl mb-8 max-w-3xl mx-auto" style="color: {theme.secondaryColor};">
                {config.hero.subheadline}
            </p>
            <div class="flex flex-col sm:flex-row gap-4 justify-center">
                <a href="{config.hero.primaryCTA.link}" class="px-8 py-4 rounded-lg font-semibold text-lg transition-all hover:scale-105" style="background-color: {theme.primaryColor}; color: white;">
                    {config.hero.primaryCTA.text}
                </a>
                {f'''<a href="{config.hero.secondaryCTA.link}" class="px-8 py-4 rounded-lg font-semibold text-lg border-2 transition-all hover:scale-105" style="border-color: {theme.primaryColor}; color: {theme.primaryColor};">
                    {config.hero.secondaryCTA.text}
                </a>''' if config.hero.secondaryCTA else ''}
            </div>
        </div>
    </section>
"""
    
    # Features Section
    if config.features:
        html += """
    <!-- Features Section -->
    <section class="py-24 px-4" style="background-color: #F9FAFB;">
        <div class="max-w-7xl mx-auto">
            <div class="text-center mb-16">
                <h2 class="text-4xl md:text-5xl font-bold mb-4" style="color: """ + theme.textColor + """;">
                    Features
                </h2>
                <p class="text-xl" style="color: """ + theme.secondaryColor + """;">
                    Everything you need to succeed
                </p>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
"""
        for feature in config.features:
            html += f"""
                <div class="p-8 rounded-2xl transition-all hover:scale-105" style="background-color: {theme.backgroundColor}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <div class="w-12 h-12 rounded-lg flex items-center justify-center mb-4" style="background-color: {theme.primaryColor}20;">
                        <svg class="w-6 h-6" style="color: {theme.primaryColor};" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                        </svg>
                    </div>
                    <h3 class="text-xl font-bold mb-2" style="color: {theme.textColor};">{feature.title}</h3>
                    <p style="color: {theme.secondaryColor};">{feature.description}</p>
                </div>
"""
        html += """
            </div>
        </div>
    </section>
"""
    
    # Products/Services Section
    if config.products:
        html += """
    <!-- Products Section -->
    <section class="py-24 px-4" style="background-color: """ + theme.backgroundColor + """;">
        <div class="max-w-7xl mx-auto">
            <div class="text-center mb-16">
                <h2 class="text-4xl md:text-5xl font-bold mb-4" style="color: """ + theme.textColor + """;">
                    Our Services
                </h2>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
"""
        for product in config.products:
            features_html = '\n'.join([f'<li class="flex items-start gap-2"><svg class="w-5 h-5 mt-0.5" style="color: {theme.primaryColor};" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg><span>{feature}</span></li>' for feature in product.features])
            
            html += f"""
                <div class="p-8 rounded-2xl border-2 transition-all hover:scale-105" style="border-color: {theme.primaryColor}30;">
                    <h3 class="text-2xl font-bold mb-2" style="color: {theme.textColor};">{product.title}</h3>
                    <div class="text-3xl font-bold mb-4" style="color: {theme.primaryColor};">{product.pricePlaceholder}</div>
                    <p class="mb-6" style="color: {theme.secondaryColor};">{product.description}</p>
                    <ul class="space-y-3 mb-6">
                        {features_html}
                    </ul>
                    <button class="w-full py-3 rounded-lg font-semibold transition-all hover:scale-105" style="background-color: {theme.primaryColor}; color: white;">
                        Get Started
                    </button>
                </div>
"""
        html += """
            </div>
        </div>
    </section>
"""
    
    # Testimonials Section
    if config.testimonials:
        html += """
    <!-- Testimonials Section -->
    <section class="py-24 px-4" style="background-color: #F9FAFB;">
        <div class="max-w-7xl mx-auto">
            <div class="text-center mb-16">
                <h2 class="text-4xl md:text-5xl font-bold mb-4" style="color: """ + theme.textColor + """;">
                    What Our Clients Say
                </h2>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
"""
        for testimonial in config.testimonials:
            html += f"""
                <div class="p-8 rounded-2xl" style="background-color: {theme.backgroundColor}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <p class="text-lg mb-4 italic" style="color: {theme.textColor};">"{testimonial.quote}"</p>
                    <div>
                        <p class="font-semibold" style="color: {theme.textColor};">{testimonial.author}</p>
                        <p class="text-sm" style="color: {theme.secondaryColor};">{testimonial.role}</p>
                    </div>
                </div>
"""
        html += """
            </div>
        </div>
    </section>
"""
    
    # Footer
    html += f"""
    <!-- Footer -->
    <footer class="py-12 px-4" style="background-color: {theme.textColor}; color: {theme.backgroundColor};">
        <div class="max-w-7xl mx-auto text-center">
            <p>&copy; 2026 {request.business_name if 'request' in dir() else 'Your Business'}. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
"""
    
    return html


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "conversapay-site-builder",
        "ai_enabled": model is not None
    }
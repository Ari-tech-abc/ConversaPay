"""Render actual delivery HTML using the offline environment of the API tests."""
import json
import runpy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_path(str(Path(__file__).with_name('test_application_security.py')), run_name='fixture_environment')
from backend.routers.frontend import _brand_markup
root = Path(__file__).resolve().parents[1]
names = ['dashboard', 'settings', 'profile', 'login', 'register', 'success', 'upgrade', 'product-import', 'onboarding']
print(json.dumps({name: _brand_markup((root/'frontend/html'/f'{name}.html').read_text(encoding='utf-8'), f'{name}.html') for name in names}))

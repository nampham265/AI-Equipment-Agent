"""Quick import verification script - run to check all modules import cleanly.

Usage (from backend/ dir):
    python verify_imports.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("Checking imports...")
errors = []

modules = [
    "app.core.config",
    "app.core.database",
    "app.core.deps",
    "app.models.equipment",
    "app.models.request",
    "app.repositories.base",
    "app.repositories.sqlite_equipment",
    "app.repositories.sqlite_request",
    "app.schemas.equipment",
    "app.schemas.requests",
    "app.schemas.agent",
    "app.schemas.manager",
    "app.ai.base",
    "app.ai.demo_provider",
    "app.ai.gemini_provider",
    "app.notifications.base",
    "app.notifications.console_provider",
    "app.notifications.email_provider",
    "app.services.equipment_service",
    "app.services.availability_service",
    "app.services.priority_service",
    "app.services.request_service",
    "app.services.approval_service",
    "app.services.notification_service",
    "app.api.equipment",
    "app.api.agent",
    "app.api.requests",
    "app.api.manager",
    "app.main",
]

for mod in modules:
    try:
        __import__(mod)
        print(f"  ✓ {mod}")
    except Exception as e:
        print(f"  ✗ {mod}: {e}")
        errors.append((mod, str(e)))

if errors:
    print(f"\n{len(errors)} import error(s) found!")
    sys.exit(1)
else:
    print(f"\nAll {len(modules)} modules imported successfully!")

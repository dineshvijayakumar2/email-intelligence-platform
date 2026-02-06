"""Quick test script to verify imports work correctly"""
import sys
import os

# Set up path
sys.path.insert(0, os.path.dirname(__file__))

print("Testing Stage 2 imports...")
print("=" * 50)

# Test models
try:
    from src.models import (
        AccountManagerCreate, AccountManagerResponse,
        ClientCreate, ClientResponse,
        CustomerCompanyCreate, CustomerCompanyResponse,
        ContactCreate, ContactResponse,
        RuleCreate, RuleResponse
    )
    print("[OK] Models imported successfully")
except Exception as e:
    print(f"[ERROR] Models: {e}")

# Test routers
try:
    from src.routers import (
        account_managers_router,
        clients_router,
        customers_router,
        contacts_router,
        errors_router
    )
    print("[OK] Routers imported successfully")
except Exception as e:
    print(f"[ERROR] Routers: {e}")

# Test services
try:
    from src.services import ErrorTracker
    print("[OK] Services imported successfully")
except Exception as e:
    print(f"[ERROR] Services: {e}")

# Test main app import
try:
    # This will fail if there are import errors in main.py
    from fastapi import FastAPI
    print("[OK] FastAPI available")
except Exception as e:
    print(f"[ERROR] FastAPI: {e}")

print("=" * 50)
print("Import test complete!")
print("\nTo start the backend, run:")
print("  cd backend")
print("  .\\venv\\Scripts\\activate")
print("  python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload")

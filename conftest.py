import os

# Set dummy env vars so scripts/generate_and_post.py can be imported in tests
# without real credentials.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("X_API_KEY", "test-key")
os.environ.setdefault("X_API_SECRET", "test-secret")
os.environ.setdefault("X_ACCESS_TOKEN", "test-token")
os.environ.setdefault("X_ACCESS_SECRET", "test-secret")

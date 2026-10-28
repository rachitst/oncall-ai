import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# offline, key-free configuration for the test suite
os.environ.update({"EMBEDDING_MODEL": "hash", "LLM_BACKEND": "mock", "CLASSIFIER_BACKEND": "rules",
                   "LOG_FILE": os.path.join(ROOT, "logs", "test.log"), "DISABLE_UI": "1"})

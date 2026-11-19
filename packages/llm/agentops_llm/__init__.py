"""Model provider adapters: deterministic mock and the LiteLLM SDK adapter."""

import os

# Runs before any submodule imports LiteLLM: use its bundled model price map instead of
# downloading one from the internet at import time.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

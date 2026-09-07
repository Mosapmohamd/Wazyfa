# Multi-Provider LLM API Support

The application now supports multiple LLM API providers through a unified interface. You can easily switch between different providers by setting environment variables.

## Supported Providers

- **NVIDIA NIM** (default)
- **OpenAI**
- **Anthropic**
- **Google Gemini**
- **Azure OpenAI**
- **Custom OpenAI-compatible APIs**

## Configuration

Set the following environment variables to configure your preferred provider:

### Basic Configuration

```bash
# Choose your provider: nvidia, openai, anthropic, google, azure, custom
export LLM_PROVIDER="openai"

# Enable external AI (required for all cloud providers)
export ALLOW_EXTERNAL_AI="true"
```

### Provider-Specific Credentials

#### NVIDIA NIM
```bash
export NVIDIA_API_KEY="your-nvidia-api-key"
export NVIDIA_FALLBACK_MODEL="meta/llama-3.1-70b-instruct"
export NVIDIA_BASE_URL="https://integrate.api.nvidia.com/v1"
```

#### OpenAI
```bash
export OPENAI_API_KEY="your-openai-api-key"
export OPENAI_MODEL="gpt-4o-mini"
```

#### Anthropic
```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export ANTHROPIC_MODEL="claude-3-haiku-20240307"
```

#### Google Gemini
```bash
export GOOGLE_API_KEY="your-google-api-key"
export GOOGLE_MODEL="gemini-1.5-flash"
```

#### Azure OpenAI
```bash
export AZURE_OPENAI_API_KEY="your-azure-api-key"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="your-deployment-name"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

#### Custom OpenAI-Compatible API
```bash
export CUSTOM_API_KEY="your-custom-api-key"
export CUSTOM_BASE_URL="https://your-custom-api.com/v1"
export CUSTOM_MODEL="your-model-name"
```

## Usage Examples

### Using OpenAI
```bash
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="sk-..."
export ALLOW_EXTERNAL_AI="true"
python main.py
```

### Using Anthropic Claude
```bash
export LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="sk-ant-..."
export ALLOW_EXTERNAL_AI="true"
python main.py
```

### Using Google Gemini
```bash
export LLM_PROVIDER="google"
export GOOGLE_API_KEY="AIza..."
export ALLOW_EXTERNAL_AI="true"
python main.py
```

### Using Azure OpenAI
```bash
export LLM_PROVIDER="azure"
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_DEPLOYMENT="..."
export ALLOW_EXTERNAL_AI="true"
python main.py
```

### Using a Custom API (e.g., Local LLM Server)
```bash
export LLM_PROVIDER="custom"
export CUSTOM_API_KEY="not-needed"
export CUSTOM_BASE_URL="http://localhost:8000/v1"
export CUSTOM_MODEL="local-model"
export ALLOW_EXTERNAL_AI="true"
python main.py
```

## Fallback Behavior

The application follows this fallback chain:

1. **External API** (configured provider via `LLM_PROVIDER`)
2. **Local LLM** (if available)
3. **NVIDIA NIM** (legacy fallback, if configured)
4. **Deterministic analysis** (keyword-based, no LLM required)

## Code Example

```python
from src.llm_client import get_llm_client
from config import settings

# Get the configured client
client = get_llm_client(settings)

# Check if available
if client.is_available():
    # Generate a response
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
    response = client.chat_completion(messages)
    print(response)
else:
    print("LLM client not available")
```

## Notes

- The `ALLOW_EXTERNAL_AI` flag must be set to `true` for any cloud provider to work (security feature).
- All credentials should be kept secure and not committed to version control.
- The application will gracefully fall back to local models or deterministic analysis if the configured provider is unavailable.

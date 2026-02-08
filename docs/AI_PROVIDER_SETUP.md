# AI Provider Setup Guide

SecIntel AI Unified now supports two AI backends for summarization:

1. **LM Studio** - Local AI using OpenAI-compatible API (free, requires local installation)
2. **Claude** - Anthropic's Claude API (cloud-based, requires API key and paid subscription)

> **RECOMMENDATION:** For most users, **LM Studio with `openai/gpt-oss-20b` is the best choice**. This local model provides comparable accuracy to Claude Haiku at zero cost.

## Quick Recommendation

| Your Situation | Recommended Provider |
|----------------|---------------------|
| Have a GPU, want free operation | **LM Studio** (Best Value) |
| No GPU, occasional use | Claude Sonnet |
| Need highest accuracy for critical reports | Claude Opus |
| Budget-conscious cloud option | **Not Haiku** - use LM Studio instead |

## Configuration Overview

The AI provider is configured in `config.yaml` under the `ai` section:

```yaml
ai:
  # Choose provider: 'lmstudio' or 'claude'
  provider: 'lmstudio'

  # LM Studio settings
  lmstudio:
    base_url: 'http://localhost:1234/v1'
    api_key: 'lm-studio'
    model: 'local-model'

  # Claude settings
  claude:
    api_key: ''  # Your Anthropic API key
    model: 'claude-sonnet-4-20250514'

  # Shared settings
  temperature: 0.1
```

## Option 1: LM Studio (Local AI)

### Advantages
- Free to use
- No data leaves your network
- Works offline
- No usage limits

### Disadvantages
- Requires local installation
- Needs GPU for good performance
- Requires downloading large model files

### Setup Steps

1. **Install LM Studio**
   - Download from https://lmstudio.ai
   - Install for your platform (Windows, macOS, Linux)

2. **Download a Model**
   - Open LM Studio
   - Go to "Discover" tab
   - Search for `openai/gpt-oss-20b` (recommended for SecIntel AI)
   - Download the model

3. **Start the Server**
   - Load your chosen model in LM Studio
   - Click "Local Server" tab
   - Click "Start Server"
   - Note the endpoint (usually http://localhost:1234/v1)

4. **Configure SecIntel AI**
   ```yaml
   ai:
     provider: 'lmstudio'
     lmstudio:
       base_url: 'http://localhost:1234/v1'
       api_key: 'lm-studio'  # Any string works
       model: 'local-model'   # Any string works
   ```

5. **Test Connection**
   ```bash
   python tests/test_ai_client.py
   ```

### Troubleshooting LM Studio

**Connection Failed**
- Ensure LM Studio server is running
- Check that the base_url matches the endpoint shown in LM Studio
- If running on a different machine, update base_url to use the machine's IP

**Slow Performance**
- Try a smaller model (7B instead of 13B)
- Use a more quantized version (Q3_K_M instead of Q4_K_M)
- Ensure you have adequate GPU memory

**Model Errors**
- Make sure a model is loaded in LM Studio before starting the server
- Try a different model if one doesn't work well

## Option 2: Claude API (Cloud-based)

> **IMPORTANT:** Claude Haiku provides minimal accuracy improvement over free local models. If using Claude API, we recommend **Sonnet or Opus only** for best results.

### Advantages
- State-of-the-art AI quality (Sonnet/Opus only)
- No local installation required
- Fast response times
- Works on any machine

### Disadvantages
- Requires paid API subscription
- Data is sent to Anthropic's servers
- Usage costs (pay per token)
- Requires internet connection
- **Haiku not recommended** - equivalent accuracy to free local models

### Setup Steps

1. **Get an Anthropic API Key**
   - Sign up at https://console.anthropic.com
   - Navigate to API Keys section
   - Create a new API key
   - Copy the key (starts with `sk-ant-`)

2. **Add Credits to Account**
   - Go to Billing section
   - Add credits (minimum $5)
   - Pricing: ~$3 per million input tokens, ~$15 per million output tokens
   - For reference, analyzing 100 articles typically uses ~$0.50-$2.00

3. **Configure SecIntel AI**
   ```yaml
   ai:
     provider: 'claude'
     claude:
       api_key: 'sk-ant-your-api-key-here'
       model: 'claude-sonnet-4-20250514'
   ```

4. **Choose a Model**
   - `claude-sonnet-4-20250514` - Recommended (fast, high quality, cost-effective)
   - `claude-opus-4-20250514` - Highest quality (slower, more expensive)
   - `claude-haiku-3-20240307` - Fastest, cheapest (lower quality)

5. **Test Connection**
   ```bash
   python tests/test_ai_client.py
   ```

### Troubleshooting Claude

**API Key Invalid**
- Verify the API key is correct (no extra spaces)
- Check that your account has credits
- Ensure the key hasn't been revoked

**Rate Limits**
- Claude has rate limits on API calls
- If you hit limits, wait a few minutes and retry
- Consider upgrading your API tier for higher limits

**Cost Management**
- Monitor usage in the Anthropic Console
- Set up billing alerts
- Start with small batches to estimate costs
- Use claude-haiku for testing to minimize costs

## Model Selection Guide

### For LM Studio

**Recommended**: `openai/gpt-oss-20b`
- Best quality summaries for security content
- Good balance of speed and accuracy
- 20B parameters, works well on modern GPUs

### For Claude

**Best Overall**: claude-sonnet-4-20250514
- Excellent quality/cost ratio
- Fast response times
- Recommended for most users

**Highest Quality**: claude-opus-4-20250514
- Best possible summaries
- Most expensive
- Use for critical analysis only

**NOT RECOMMENDED**: claude-3-haiku-20240307
- Minimal accuracy improvement over free local models
- No cost benefit over LM Studio
- If budget is a concern, use LM Studio instead (free)

## Switching Between Providers

You can easily switch between providers by changing the `provider` field:

```yaml
# Use LM Studio
ai:
  provider: 'lmstudio'
  # ... lmstudio config ...

# Switch to Claude
ai:
  provider: 'claude'
  # ... claude config ...
```

No other code changes are required. The system will automatically use the selected provider for all summarization tasks.

## Cost Comparison

### LM Studio
- **Setup Cost**: Free
- **Per-Article Cost**: $0 (after GPU purchase)
- **Best For**: High-volume processing, privacy-sensitive data

### Claude API
- **Setup Cost**: $0
- **Per-Article Cost**: ~$0.005-$0.02 per article (depending on model)
- **100 Articles**: ~$0.50-$2.00
- **Best For**: Highest quality summaries, no local infrastructure

## Performance Comparison

Based on typical SecIntel AI usage:

| Metric | LM Studio (gpt-oss-20b) | Claude Sonnet 4 |
|--------|-------------------------|-----------------|
| Quality | Good | Excellent |
| Speed | 5-15 sec/article | 2-5 sec/article |
| Cost | $0 | ~$0.01/article |
| Privacy | Full local control | Cloud-based |
| Setup | Complex | Simple |

## Backwards Compatibility

Existing SecIntel AI installations will continue to work without changes. The old configuration format is automatically detected and converted to the new format internally.

Old format (still supported):
```yaml
ai:
  base_url: 'http://localhost:1234/v1'
  api_key: 'lm-studio'
  model: 'local-model'
  temperature: 0.1
```

New format (recommended):
```yaml
ai:
  provider: 'lmstudio'
  lmstudio:
    base_url: 'http://localhost:1234/v1'
    api_key: 'lm-studio'
    model: 'local-model'
  temperature: 0.1
```

## Testing Your Setup

Run the test suite to verify your configuration:

```bash
python tests/test_ai_client.py
```

This will test:
1. Configuration loading
2. Backwards compatibility
3. AI client initialization
4. Connection to your selected provider
5. Summarizer compatibility

## Next Steps

After configuring your AI provider:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run a full SecIntel AI workflow:
   ```bash
   python secintel.py --full-run
   ```

3. Monitor the logs to ensure AI summarization is working correctly

4. Check the generated reports in the `reports/` directory

## Support

For issues:
- LM Studio: https://lmstudio.ai/docs
- Claude API: https://docs.anthropic.com
- SecIntel AI: Check the main README.md or open an issue

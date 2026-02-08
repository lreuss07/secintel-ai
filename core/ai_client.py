"""
Unified AI client for SecIntel AI.

Provides a common interface for both LM Studio (OpenAI-compatible) and Claude API,
allowing seamless switching between local and cloud-based AI providers.
"""

import logging
from typing import List, Dict, Optional
from openai import OpenAI
import anthropic

logger = logging.getLogger(__name__)


class AIClient:
    """
    Unified AI client supporting multiple providers.

    Supports:
    - LM Studio (OpenAI-compatible local API)
    - Claude (Anthropic cloud API)
    """

    def __init__(self, config: Dict):
        """
        Initialize the AI client with configuration.

        Args:
            config (dict): AI configuration dictionary containing:
                - provider: 'lmstudio' or 'claude'
                - lmstudio: {base_url, api_key, model} (if provider is lmstudio)
                - claude: {api_key, model} (if provider is claude)
                - temperature: float (shared setting)
        """
        self.config = config
        self.provider = config.get('provider', 'lmstudio').lower()
        self.temperature = config.get('temperature', 0.1)
        self.client = None
        self.model = None

        # Initialize the appropriate client
        if self.provider == 'lmstudio':
            self._init_lmstudio()
        elif self.provider == 'claude':
            self._init_claude()
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}. Use 'lmstudio' or 'claude'.")

    def _init_lmstudio(self):
        """Initialize LM Studio client."""
        lm_config = self.config.get('lmstudio', {})

        # Support legacy config format (backwards compatibility)
        if not lm_config and 'base_url' in self.config:
            logger.warning("Using legacy AI config format. Consider updating to new format with 'provider' and provider-specific settings.")
            lm_config = {
                'base_url': self.config.get('base_url', 'http://localhost:1234/v1'),
                'api_key': self.config.get('api_key', 'lm-studio'),
                'model': self.config.get('model', 'local-model')
            }

        base_url = lm_config.get('base_url', 'http://localhost:1234/v1')
        api_key = lm_config.get('api_key', 'lm-studio')
        self.model = lm_config.get('model', 'local-model')

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        logger.info(f"Initialized LM Studio client at {base_url} with model {self.model}")

    def _init_claude(self):
        """Initialize Claude client."""
        claude_config = self.config.get('claude', {})

        api_key = claude_config.get('api_key')
        if not api_key:
            raise ValueError("Claude API key not configured. Set 'ai.claude.api_key' in config.yaml")

        self.model = claude_config.get('model', 'claude-sonnet-4-20250514')
        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info(f"Initialized Claude client with model {self.model}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: Optional[float] = None
    ) -> str:
        """
        Generate a chat completion using the configured AI provider.

        Args:
            messages (list): List of message dicts with 'role' and 'content'
            max_tokens (int): Maximum tokens to generate
            temperature (float, optional): Temperature override (uses config default if None)

        Returns:
            str: Generated text response
        """
        temp = temperature if temperature is not None else self.temperature

        if self.provider == 'lmstudio':
            return self._lmstudio_completion(messages, max_tokens, temp)
        elif self.provider == 'claude':
            return self._claude_completion(messages, max_tokens, temp)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _lmstudio_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float
    ) -> str:
        """
        Generate completion using LM Studio (OpenAI-compatible API).

        Args:
            messages (list): List of message dicts with 'role' and 'content'
            max_tokens (int): Maximum tokens to generate
            temperature (float): Temperature setting

        Returns:
            str: Generated text
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LM Studio completion error: {str(e)}")
            raise

    def _claude_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float
    ) -> str:
        """
        Generate completion using Claude API.

        Claude API expects a different format:
        - System message goes in 'system' parameter (not in messages list)
        - Messages must alternate between 'user' and 'assistant'

        Args:
            messages (list): List of message dicts with 'role' and 'content'
            max_tokens (int): Maximum tokens to generate
            temperature (float): Temperature setting

        Returns:
            str: Generated text
        """
        try:
            # Extract system message if present
            system_message = None
            conversation_messages = []

            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                else:
                    conversation_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })

            # Ensure messages alternate between user and assistant
            # If the list doesn't alternate properly, Claude API will error
            # For now, we'll assume proper alternation (most common case)

            # Call Claude API
            if system_message:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_message,
                    messages=conversation_messages
                )
            else:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=conversation_messages
                )

            # Extract text from response
            # Claude response format: response.content is a list of content blocks
            text_content = []
            for block in response.content:
                if block.type == 'text':
                    text_content.append(block.text)

            return '\n'.join(text_content).strip()

        except Exception as e:
            logger.error(f"Claude completion error: {str(e)}")
            raise

    def test_connection(self) -> bool:
        """
        Test the AI provider connection.

        Returns:
            bool: True if connection successful, False otherwise
        """
        logger.info(f"Testing {self.provider} connection...")

        try:
            test_messages = [
                {"role": "user", "content": "Hello! Please respond with 'OK' if you can hear me."}
            ]

            response = self.chat_completion(
                messages=test_messages,
                max_tokens=50,
                temperature=0.0
            )

            logger.info(f"{self.provider.title()} response: {response}")
            logger.info(f"Connection to {self.provider} successful!")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.provider}: {str(e)}")
            return False

    def get_provider(self) -> str:
        """Get the current provider name."""
        return self.provider

    def get_model(self) -> str:
        """Get the current model name."""
        return self.model

    def classify_content(self, title: str, content: str) -> str:
        """
        Classify article content into one of three categories using AI.

        This pre-classification step prevents hallucination of threat content
        in non-threat articles by determining the appropriate summarization approach.

        Args:
            title (str): Article title
            content (str): Article content (first 2000 chars recommended for speed)

        Returns:
            str: One of 'threat_advisory', 'product_update', or 'industry_news'
        """
        # Truncate content to first 2000 chars for faster classification
        content_sample = content[:2000] if len(content) > 2000 else content

        classification_prompt = f"""You are a cybersecurity content classifier. Classify the following article into ONE of these categories:

1. **threat_advisory** - Articles about:
   - CVEs, vulnerabilities, security patches
   - Malware analysis, threat actor reports
   - Breach reports, incident analysis
   - Active exploitation, attack campaigns
   - IOCs (Indicators of Compromise)
   - Security advisories and alerts

2. **product_update** - Articles about:
   - Vendor product changelogs
   - Feature announcements and release notes
   - Product updates and new capabilities
   - Beta/preview feature releases
   - Version updates and roadmaps

3. **industry_news** - Articles about:
   - General cybersecurity news
   - Opinion pieces and editorials
   - Policy updates and regulations
   - Industry trends and analysis
   - Explainer articles and how-to guides
   - Company announcements
   - Market analysis and research

Title: {title}

Content (first 2000 characters):
{content_sample}

Respond with ONLY ONE WORD - the category name (threat_advisory, product_update, or industry_news).
Do not include any explanation or additional text."""

        try:
            response = self.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise content classifier. Respond with only the category name, nothing else."
                    },
                    {
                        "role": "user",
                        "content": classification_prompt
                    }
                ],
                max_tokens=50,  # Increased to handle model variations
                temperature=0.0  # Deterministic classification
            )

            # Clean and validate the response
            classification = response.strip().lower()

            # Remove any extra text (some models might add punctuation or explanation)
            classification = classification.split()[0] if ' ' in classification else classification
            classification = classification.strip('.,!?')

            # Validate the classification
            valid_categories = ['threat_advisory', 'product_update', 'industry_news']

            if classification in valid_categories:
                logger.info(f"Classified '{title[:50]}...' as '{classification}'")
                return classification
            else:
                # Try to match partial responses
                for category in valid_categories:
                    if category in classification or classification in category:
                        logger.warning(f"Partial match: '{classification}' matched to '{category}'")
                        return category

                # Default to industry_news if classification unclear (safest option)
                logger.warning(f"Invalid classification '{classification}' for '{title[:50]}...', defaulting to 'industry_news'")
                return 'industry_news'

        except Exception as e:
            logger.error(f"Error classifying content: {str(e)}")
            # Default to industry_news on error (safest to avoid hallucination)
            return 'industry_news'


class AIClientFactory:
    """Factory for creating AI clients from configuration."""

    @staticmethod
    def create_from_config(config: Dict) -> AIClient:
        """
        Create an AI client from configuration dictionary.

        Args:
            config (dict): AI configuration

        Returns:
            AIClient: Configured AI client instance
        """
        return AIClient(config)

    @staticmethod
    def create_lmstudio(
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        model: str = "local-model",
        temperature: float = 0.1
    ) -> AIClient:
        """
        Create an LM Studio AI client.

        Args:
            base_url (str): LM Studio endpoint URL
            api_key (str): API key (any string works)
            model (str): Model name
            temperature (float): Temperature setting

        Returns:
            AIClient: LM Studio client
        """
        config = {
            'provider': 'lmstudio',
            'lmstudio': {
                'base_url': base_url,
                'api_key': api_key,
                'model': model
            },
            'temperature': temperature
        }
        return AIClient(config)

    @staticmethod
    def create_claude(
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.1
    ) -> AIClient:
        """
        Create a Claude AI client.

        Args:
            api_key (str): Anthropic API key
            model (str): Claude model name
            temperature (float): Temperature setting

        Returns:
            AIClient: Claude client
        """
        config = {
            'provider': 'claude',
            'claude': {
                'api_key': api_key,
                'model': model
            },
            'temperature': temperature
        }
        return AIClient(config)

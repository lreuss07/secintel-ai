"""
LM Studio connection management for SecIntel AI.

Handles connection testing, fallback to alternative endpoints,
and graceful error handling when LM Studio is unavailable.
"""

import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Default LM Studio endpoint
DEFAULT_LM_STUDIO_ENDPOINT = "http://localhost:1234/v1"


class LMStudioConnectionManager:
    """Manages LM Studio connections with fallback support"""

    def __init__(self, config=None):
        """
        Initialize the connection manager.

        Args:
            config (dict): AI configuration with base_url, api_key, model
        """
        self.config = config or {}
        self.base_url = self.config.get('base_url', DEFAULT_LM_STUDIO_ENDPOINT)
        self.api_key = self.config.get('api_key', 'lm-studio')
        self.model = self.config.get('model', 'local-model')
        self.client = None
        self.connection_verified = False

    def test_connection(self, endpoint=None, silent=False):
        """
        Test connection to LM Studio endpoint.

        Args:
            endpoint (str, optional): Endpoint to test. If None, uses configured endpoint
            silent (bool): If True, suppress log messages

        Returns:
            bool: True if connection successful, False otherwise
        """
        test_url = endpoint or self.base_url

        if not silent:
            logger.info(f"Testing LM Studio connection to: {test_url}")

        try:
            client = OpenAI(
                base_url=test_url,
                api_key=self.api_key
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Hello! Please respond with 'OK' if you can hear me."}
                ],
                max_tokens=50,
                temperature=0.0
            )

            response_text = response.choices[0].message.content
            if not silent:
                logger.info(f"LM Studio response: {response_text}")
                logger.info("Connection to LM Studio successful!")

            # Update connection if successful
            if endpoint:
                self.base_url = endpoint
                self.config['base_url'] = endpoint

            self.client = client
            self.connection_verified = True
            return True

        except Exception as e:
            if not silent:
                logger.error(f"Failed to connect to LM Studio at {test_url}: {str(e)}")
            return False

    def ensure_connection(self, allow_prompt=True):
        """
        Ensure LM Studio connection is established.

        First tries the default endpoint (localhost:1234/v1),
        then tries the configured endpoint if different,
        then prompts user for alternative if allowed and all attempts fail.

        Args:
            allow_prompt (bool): If True, prompts user for alternative endpoint on failure

        Returns:
            bool: True if connection established, False otherwise
        """
        # If already verified, return success
        if self.connection_verified:
            return True

        # Try configured endpoint first (if different from default)
        logger.info("=" * 70)
        logger.info("Checking LM Studio connection")
        logger.info("=" * 70)

        # If a custom endpoint is configured, try it first
        if self.base_url != DEFAULT_LM_STUDIO_ENDPOINT:
            if self.test_connection(self.base_url, silent=False):
                return True
            logger.warning(f"Configured endpoint failed. Trying default endpoint: {DEFAULT_LM_STUDIO_ENDPOINT}")

        # Try default endpoint
        if self.test_connection(DEFAULT_LM_STUDIO_ENDPOINT, silent=False):
            return True

        # All automatic attempts failed
        logger.error("Could not connect to LM Studio at default or configured endpoints")

        if not allow_prompt:
            logger.error("Connection failed and prompting is disabled")
            return False

        # Prompt user for alternative endpoint
        logger.info("")
        logger.info("=" * 70)
        logger.info("LM Studio Connection Failed")
        logger.info("=" * 70)
        logger.info("Please ensure LM Studio is running with a model loaded.")
        logger.info("")
        logger.info("You can:")
        logger.info("  1. Start LM Studio at the default endpoint (http://localhost:1234/v1)")
        logger.info("  2. Provide an alternative endpoint below")
        logger.info("  3. Press Enter to cancel")
        logger.info("")

        try:
            user_endpoint = input("Enter LM Studio endpoint URL (or press Enter to cancel): ").strip()

            if not user_endpoint:
                logger.warning("No endpoint provided. Operations requiring LM Studio will fail.")
                return False

            # Ensure endpoint has proper format
            if not user_endpoint.startswith('http://') and not user_endpoint.startswith('https://'):
                user_endpoint = f"http://{user_endpoint}"

            # Add /v1 suffix if not present
            if not user_endpoint.endswith('/v1'):
                user_endpoint = f"{user_endpoint}/v1"

            logger.info(f"Testing user-provided endpoint: {user_endpoint}")

            if self.test_connection(user_endpoint, silent=False):
                logger.info(f"Successfully connected to LM Studio at: {user_endpoint}")
                logger.info("This endpoint will be used for the current session")
                logger.info("To make this permanent, update the 'base_url' in your config.yaml")
                return True
            else:
                logger.error(f"Failed to connect to: {user_endpoint}")
                logger.error("Operations requiring LM Studio will fail.")
                return False

        except (KeyboardInterrupt, EOFError):
            logger.warning("\nConnection setup cancelled by user")
            return False
        except Exception as e:
            logger.error(f"Error during connection setup: {str(e)}")
            return False

    def get_client(self):
        """
        Get configured OpenAI client for LM Studio.

        Returns:
            OpenAI: Configured client instance or None if not connected
        """
        if not self.connection_verified:
            logger.warning("LM Studio connection not verified. Call ensure_connection() first.")
            return None

        if not self.client:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )

        return self.client

    def get_config(self):
        """
        Get current connection configuration.

        Returns:
            dict: Configuration dict with base_url, api_key, model
        """
        return {
            'base_url': self.base_url,
            'api_key': self.api_key,
            'model': self.model
        }

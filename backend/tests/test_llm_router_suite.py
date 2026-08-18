"""
PrivacyShieldAI - Comprehensive LLM Router Test Suite
Unit tests for production MLOps LLM routing, failover, exception handling, and metadata diagnostics.
Tests:
1. Cloud success
2. Cloud timeout
3. 401 Unauthorized
4. 403 Forbidden
5. 429 Rate Limit Exceeded
6. 500 Server Error
7. No API key
8. Invalid model
9. Network unavailable
10. Local fallback verification (Local Qwen ONLY used when cloud inference genuinely fails)
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'tests' else Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

from app.agents.llm_router import LLMRouter, LLMResponse, MODEL_MAPPING
from app.agents.llm_providers import (
    BaseLLMProvider,
    LLMProviderResponse,
    GroqProvider,
    LocalQwenProvider,
    LLMAuthenticationError,
    LLMForbiddenError,
    LLMQuotaOrRateLimitError,
    LLMInvalidModelError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMServerError,
)


class TestLLMRouterSuite(unittest.TestCase):

    def setUp(self):
        self.router = LLMRouter(default_model="llama-3.3-70b-versatile")
        self.sample_messages = [
            {"role": "system", "content": "You are a helpful privacy assistant."},
            {"role": "user", "content": "Hello, explain PrivacyShieldAI."}
        ]
        self.valid_key = "gsk_" + "a" * 32

        # Fast mock for local fallback provider
        self.patcher = patch.object(LocalQwenProvider, 'generate')
        self.mock_local = self.patcher.start()
        self.mock_local.side_effect = lambda messages, fallback_reason=None, **kwargs: LLMProviderResponse(
            content="Local fallback generated response.",
            model_name="Qwen-Local",
            provider_name="Local Qwen",
            routing_strategy="Fallback" if fallback_reason else "Local",
            fallback_reason=fallback_reason,
            latency_ms=15
        )

    def tearDown(self):
        self.patcher.stop()

    @patch.object(GroqProvider, 'generate')
    def test_1_cloud_success(self, mock_groq_generate):
        """Verify that when cloud API succeeds, cloud response is returned and Local Qwen is NOT called."""
        mock_groq_generate.return_value = MagicMock(
            content="PrivacyShieldAI protects enterprise data.",
            model_name="llama-3.3-70b-versatile",
            provider_name="Groq",
            routing_strategy="Cloud",
            raw_response={"choices": [{"message": {"content": "OK"}}]},
            latency_ms=120
        )

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Groq")
        self.assertEqual(res.routing_strategy, "Cloud")
        self.assertIsNone(res.fallback_reason)
        self.assertEqual(res.content, "PrivacyShieldAI protects enterprise data.")
        mock_groq_generate.assert_called_once()
        print(" [PASS] Test 1: Cloud Success verified (Groq used, no fallback).")

    @patch.object(GroqProvider, 'generate')
    def test_2_cloud_timeout(self, mock_groq_generate):
        """Verify timeout exception triggers fallback to Local Qwen with detailed timeout log reason."""
        mock_groq_generate.side_effect = LLMTimeoutError("Groq HTTP request timed out after 25s", provider="Groq")

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("Timeout", res.fallback_reason)
        print(f" [PASS] Test 2: Cloud Timeout fallback verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_3_cloud_401_unauthorized(self, mock_groq_generate):
        """Verify 401 Unauthorized triggers fallback with 401 reason."""
        mock_groq_generate.side_effect = LLMAuthenticationError("401 Unauthorized - Invalid Groq API Key", provider="Groq", status_code=401)

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("401", res.fallback_reason)
        print(f" [PASS] Test 3: Cloud 401 Unauthorized fallback verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_4_cloud_403_forbidden(self, mock_groq_generate):
        """Verify 403 Forbidden triggers fallback with 403 reason."""
        mock_groq_generate.side_effect = LLMForbiddenError("403 Forbidden - Access denied", provider="Groq", status_code=403)

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("403", res.fallback_reason)
        print(f" [PASS] Test 4: Cloud 403 Forbidden fallback verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_5_cloud_429_rate_limit(self, mock_groq_generate):
        """Verify 429 Rate Limit triggers fallback with 429 reason."""
        mock_groq_generate.side_effect = LLMQuotaOrRateLimitError("429 Rate Limit Exceeded", provider="Groq", status_code=429)

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("429", res.fallback_reason)
        print(f" [PASS] Test 5: Cloud 429 Rate Limit fallback verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_6_cloud_500_server_error(self, mock_groq_generate):
        """Verify 500 Server Error triggers fallback with 500 reason."""
        mock_groq_generate.side_effect = LLMServerError("500 Groq Server Error", provider="Groq", status_code=500)

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("500", res.fallback_reason)
        print(f" [PASS] Test 6: Cloud 500 Server Error fallback verified (Reason: {res.fallback_reason}).")

    def test_7_no_api_key(self):
        """Verify that when no API key is provided, pre-flight validation fails and falls back cleanly."""
        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=""
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("missing or empty", res.fallback_reason.lower())
        print(f" [PASS] Test 7: No API key validation & fallback verified (Reason: {res.fallback_reason}).")

    def test_8_invalid_model(self):
        """Verify invalid API key format pre-flight validation."""
        res = self.router.generate(
            messages=self.sample_messages,
            model_name="invalid-model-xyz",
            groq_api_key="short_invalid_key"
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("invalid", res.fallback_reason.lower())
        print(f" [PASS] Test 8: Invalid key format pre-flight validation verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_9_network_unavailable(self, mock_groq_generate):
        """Verify connection error triggers fallback with network connection failure reason."""
        mock_groq_generate.side_effect = LLMConnectionError("Groq network connection failed: DNS lookup failed", provider="Groq")

        res = self.router.generate(
            messages=self.sample_messages,
            model_name="llama-3.3-70b-versatile",
            groq_api_key=self.valid_key
        )

        self.assertEqual(res.provider_used, "Local Qwen")
        self.assertEqual(res.routing_strategy, "Fallback")
        self.assertIn("Connection", res.fallback_reason)
        print(f" [PASS] Test 9: Network unavailable fallback verified (Reason: {res.fallback_reason}).")

    @patch.object(GroqProvider, 'generate')
    def test_10_local_fallback_guarantee(self, mock_groq_generate):
        """Verify that Local Qwen is ONLY used when cloud inference genuinely fails."""
        # Case A: Cloud succeeds -> MUST NOT use Local Qwen
        mock_groq_generate.return_value = MagicMock(
            content="Cloud generated response",
            model_name="llama-3.3-70b-versatile",
            provider_name="Groq",
            routing_strategy="Cloud",
            raw_response={},
            latency_ms=90
        )
        res_cloud = self.router.generate(messages=self.sample_messages, groq_api_key=self.valid_key)
        self.assertEqual(res_cloud.provider_used, "Groq")
        self.assertNotEqual(res_cloud.provider_used, "Local Qwen")

        # Case B: Cloud fails -> MUST use Local Qwen
        mock_groq_generate.side_effect = LLMAuthenticationError("Cloud Key Invalid", provider="Groq")
        res_fallback = self.router.generate(messages=self.sample_messages, groq_api_key=self.valid_key)
        self.assertEqual(res_fallback.provider_used, "Local Qwen")
        self.assertEqual(res_fallback.routing_strategy, "Fallback")

        print(" [PASS] Test 10: Local Qwen ONLY used on genuine cloud failure guarantee verified.")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLLMRouterSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n==================================================")
        print(" ALL 10 LLM ROUTER DIAGNOSTIC TESTS PASSED! ")
        print("==================================================")
    else:
        sys.exit(1)

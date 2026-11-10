import json
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import ai_pr_test_review as reviewer


class FakeHTTPError:
    def __init__(self, code, reason, body):
        self.code = code
        self.reason = reason
        self._body = body

    def read(self, limit):
        return self._body[:limit]


class ReviewInputTests(unittest.TestCase):
    def test_uses_supported_flash_lite_model_and_endpoint(self):
        self.assertEqual(reviewer.MODEL, "gemini-3.1-flash-lite")
        self.assertTrue(reviewer.ENDPOINT.endswith(
            "/v1beta/models/gemini-3.1-flash-lite:generateContent"
        ))

    def test_model_preflight_accepts_exact_model_with_generate_content(self):
        payload = {"models": [{
            "name": "models/gemini-3.1-flash-lite",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        }]}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload).encode()

        with mock.patch.object(reviewer.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
            self.assertTrue(reviewer.model_supports_generate_content("test-key"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, reviewer.MODELS_ENDPOINT + "?pageSize=100")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")

    def test_model_preflight_rejects_model_without_generate_content(self):
        payload = {"models": [{
            "name": "models/gemini-3.1-flash-lite",
            "supportedGenerationMethods": ["countTokens"],
        }]}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload).encode()

        with mock.patch.object(reviewer.urllib.request, "urlopen", return_value=FakeResponse()):
            self.assertFalse(reviewer.model_supports_generate_content("test-key"))

    def test_model_preflight_rejects_unlisted_model(self):
        payload = {"models": [{"name": "models/gemini-2.5-flash",
                               "supportedGenerationMethods": ["generateContent"]}]}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload).encode()

        with mock.patch.object(reviewer.urllib.request, "urlopen", return_value=FakeResponse()):
            self.assertFalse(reviewer.model_supports_generate_content("test-key"))

    def test_generation_payload_omits_deprecated_sampling_parameters(self):
        payload = reviewer.build_payload("system rules", "review this diff")
        self.assertEqual(
            payload["generationConfig"],
            {
                "maxOutputTokens": reviewer.MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
            },
        )
        self.assertEqual(payload["contents"][0]["role"], "user")

    def test_only_reviewable_source_and_workflow_files_are_included(self):
        self.assertTrue(reviewer.reviewable_path("src/backend/authenticator.py"))
        self.assertTrue(reviewer.reviewable_path(".github/workflows/ci.yml"))
        self.assertFalse(reviewer.reviewable_path(".env.production"))
        self.assertFalse(reviewer.reviewable_path("secrets/private.py"))
        self.assertFalse(reviewer.reviewable_path("src/frontend/package-lock.json"))
        self.assertFalse(reviewer.reviewable_path("certificates/signing.pem"))

    def test_common_provider_and_repository_tokens_are_redacted(self):
        sample = (
            "id=github_pat_abcdefghijklmnopqrstuvwxyz1234567890 "
            "AIza0123456789abcdefghijklmnopqrstuvwxyzABCDE"
        )
        result = reviewer.redact(sample)
        self.assertNotIn("github_pat_", result)
        self.assertNotIn("AIza", result)
        self.assertGreaterEqual(result.count("[REDACTED_SECRET]"), 2)

    def test_secret_like_environment_assignments_are_redacted(self):
        sample = 'GEMINI_API_KEY = "supersecretvalue123"'
        result = reviewer.redact(sample)
        self.assertIn("GEMINI_API_KEY", result)
        self.assertNotIn("supersecretvalue123", result)
        self.assertIn("[REDACTED]", result)

    def test_bearer_credentials_and_private_keys_are_redacted(self):
        bearer = reviewer.redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz")
        pem = reviewer.redact(
            "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----"
        )
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", bearer)
        self.assertNotIn("private-material", pem)

    def test_summary_text_is_html_escaped_and_bounded(self):
        result = reviewer.safe('<script>alert("x")</script>|bad', 100)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn(r"\|", result)

    def test_http_error_summary_reports_status_and_safe_provider_message(self):
        body = json.dumps({
            "error": {
                "message": "API key not valid. Example leaked key AIza0123456789abcdefghijklmnopqrstuvwxyzABCDE"
            }
        }).encode()
        error = FakeHTTPError(403, "Forbidden", body)
        result = reviewer.http_error_summary(error)
        self.assertIn("GEMINI_API_ERROR: HTTP 403", result)
        self.assertIn("API key not valid", result)
        self.assertNotIn("AIza", result)

    def test_http_error_summary_includes_structured_status_and_safe_detail(self):
        body = json.dumps({
            "error": {
                "code": 404,
                "status": "NOT_FOUND",
                "message": "Model gemini-3.1-flash-lite was not found",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "MODEL_NOT_FOUND",
                        "domain": "generativelanguage.googleapis.com",
                        "metadata": {
                            "api_key": "must-not-be-logged",
                            "project": "private-project"
                        }
                    }
                ],
            }
        }).encode()
        error = FakeHTTPError(404, "Not Found", body)
        result = reviewer.http_error_summary(error)
        self.assertIn("HTTP 404", result)
        self.assertIn("status=NOT_FOUND", result)
        self.assertIn("MODEL_NOT_FOUND", result)
        self.assertIn("generativelanguage.googleapis.com", result)
        self.assertNotIn("must-not-be-logged", result)
        self.assertNotIn("private-project", result)

    def test_http_error_summary_handles_non_json_provider_response(self):
        error = FakeHTTPError(429, "Too Many Requests", b"not-json")
        result = reviewer.http_error_summary(error)
        self.assertIn("GEMINI_API_ERROR: HTTP 429", result)
        self.assertIn("Too Many Requests", result)


if __name__ == "__main__":
    unittest.main()

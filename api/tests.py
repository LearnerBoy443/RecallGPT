from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
import os

class ImageGenerationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        self.client.force_authenticate(user=self.user)
        self.url = reverse('api_generate_image')

    @patch('api.views.requests.post')
    def test_image_generation_flux_schnell(self, mock_post):
        with patch.dict(os.environ, {"HF_TOKEN": "mock_token"}):
            mock_post.return_value.status_code = 200
            mock_post.return_value.content = b"\x89PNGfakeimagebytes"
            
            response = self.client.post(self.url, {
                "prompt": "A futuristic city",
                "model": "flux_schnell"
            }, format="json")
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("image_url", response.data)
            self.assertEqual(response.data["model_used"], "black-forest-labs/FLUX.1-schnell")
            self.assertEqual(response.data["fallback"], False)
            
            mock_post.assert_called_once_with(
                "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                headers={"Authorization": "Bearer mock_token"},
                json={
                    "inputs": "A futuristic city",
                    "options": {"wait_for_model": True}
                },
                timeout=60
            )

    @patch('api.views.requests.post')
    def test_image_generation_sdxl_base(self, mock_post):
        with patch.dict(os.environ, {"HF_TOKEN": "mock_token"}):
            mock_post.return_value.status_code = 200
            mock_post.return_value.content = b"\x89PNGfakeimagebytes"
            
            response = self.client.post(self.url, {
                "prompt": "A beautiful sunset",
                "model": "sdxl_base"
            }, format="json")
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("image_url", response.data)
            self.assertEqual(response.data["model_used"], "stabilityai/stable-diffusion-xl-base-1.0")
            self.assertEqual(response.data["fallback"], False)
            
            mock_post.assert_called_once_with(
                "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0",
                headers={"Authorization": "Bearer mock_token"},
                json={
                    "inputs": "A beautiful sunset",
                    "options": {"wait_for_model": True}
                },
                timeout=60
            )

    @patch('api.views.requests.post')
    def test_image_generation_sd_15(self, mock_post):
        with patch.dict(os.environ, {"HF_TOKEN": "mock_token"}):
            mock_post.return_value.status_code = 200
            mock_post.return_value.content = b"\x89PNGfakeimagebytes"
            
            response = self.client.post(self.url, {
                "prompt": "A cute cat",
                "model": "sd_15"
            }, format="json")
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("image_url", response.data)
            self.assertEqual(response.data["model_used"], "runwayml/stable-diffusion-v1-5")
            self.assertEqual(response.data["fallback"], False)
            
            mock_post.assert_called_once_with(
                "https://router.huggingface.co/hf-inference/models/runwayml/stable-diffusion-v1-5",
                headers={"Authorization": "Bearer mock_token"},
                json={
                    "inputs": "A cute cat",
                    "options": {"wait_for_model": True}
                },
                timeout=60
            )

    @patch('api.views.requests.post')
    def test_image_generation_fallback(self, mock_post):
        with patch.dict(os.environ, {"HF_TOKEN": "mock_token"}):
            # Create two mock responses: first one fails, second succeeds
            mock_resp_fail = MagicMock()
            mock_resp_fail.status_code = 500
            mock_resp_fail.content = b"Internal Server Error"
            
            mock_resp_success = MagicMock()
            mock_resp_success.status_code = 200
            mock_resp_success.content = b"\x89PNGfakeimagebytes"
            
            mock_post.side_effect = [mock_resp_fail, mock_resp_success]
            
            response = self.client.post(self.url, {
                "prompt": "A cute cat",
                "model": "flux_schnell"
            }, format="json")
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("image_url", response.data)
            self.assertEqual(response.data["model_used"], "runwayml/stable-diffusion-v1-5")
            self.assertEqual(response.data["fallback"], True)
            
            # Check mock_post was called with both urls in sequence
            self.assertEqual(mock_post.call_count, 2)
            calls = mock_post.call_args_list
            
            self.assertEqual(calls[0][0][0], "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell")
            self.assertEqual(calls[1][0][0], "https://router.huggingface.co/hf-inference/models/runwayml/stable-diffusion-v1-5")

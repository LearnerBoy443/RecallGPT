from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from django.conf import settings
from pathlib import Path
import os

from api.services import get_qa_chain
from parsers import aggregate_notes, parse_tasks_and_expenses

class QAChainTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="qauser", password="testpassword")

    def test_parses_task_and_finance_from_natural_language_note(self):
        note_text = (
            "Task: I need to finish the quarterly report by Friday and send it to the client for review. "
            "Finance: I paid $120 for office supplies and received $500 from a client payment today."
        )

        tasks, expenses = parse_tasks_and_expenses(note_text)

        self.assertEqual(len(tasks), 1)
        self.assertIn("finish the quarterly report", tasks[0]["task"])
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0]["category"], "office supplies")
        self.assertEqual(expenses[0]["amount"], 120.0)

    def test_selected_notes_fallback_to_unfiltered_search_when_filter_returns_no_results(self):
        class FakeDoc:
            def __init__(self, page_content):
                self.page_content = page_content
             
        class FakePGVector:
            def __init__(self, *args, **kwargs):
                self.filter_calls = 0
                self.unfiltered_calls = 0
 
            def similarity_search(self, query, k=3, filter=None):
                if filter is not None:
                    self.filter_calls += 1
                    return []
                self.unfiltered_calls += 1
                return [FakeDoc("Task: finish the report. Finance: paid $120.")]
 
        fake_llm = MagicMock()
        fake_llm.invoke.return_value.content = "Handled via fallback"
 
        with patch('api.services.get_db_connection_string', return_value='postgresql://user:pass@localhost:5432/test'), \
             patch('api.services.get_embedding_model', return_value=object()), \
             patch('langchain_community.vectorstores.PGVector', return_value=FakePGVector()), \
             patch('langchain_nvidia_ai_endpoints.ChatNVIDIA', return_value=fake_llm):
            qa_chain = get_qa_chain(self.user.id)
            response = qa_chain.run('What is the task?', selected_notes=['test.md'])
 
        self.assertEqual(response, 'Handled via fallback')
 
    def test_aggregate_notes_falls_back_to_local_notes_when_no_database_files(self):
        notes_dir = Path(settings.BASE_DIR) / 'notes'
        notes_dir.mkdir(exist_ok=True)
        test_file = notes_dir / 'local_fallback_test.md'
        test_file.write_text(
            'Task: submit the expense sheet by Friday.\nFinance: Spent $45 on printer ink.\n',
            encoding='utf-8'
        )
        try:
            tasks, expenses = aggregate_notes(user_id=999999999)
            self.assertTrue(any('submit the expense sheet' in task['task'] for task in tasks))
            self.assertTrue(any(expense['amount'] == 45.0 for expense in expenses))
        finally:
            if test_file.exists():
                test_file.unlink()


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

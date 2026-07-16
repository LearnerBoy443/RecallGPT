import os
import re
import time
import uuid
import requests
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login, logout as auth_logout
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse
import json
from .services import retrain_vector_db, get_qa_chain
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from .models import ChatSession, ChatMessage, UserProfile, ImageMemory, DatabaseFile
from .serializers import ChatSessionSerializer, ChatMessageSerializer, TaskSerializer, ExpenseSerializer
from .utils import (
    get_image_context,
    extract_exif_metadata,
    extract_keywords_from_text,
    find_matching_images,
    format_image_recall_markdown,
)
from django.db.models import Q, Count
from parsers import aggregate_notes, invalidate_aggregate_notes_cache


# ---------------------------------------------------------------------------
# Cloud AI Helper
# ---------------------------------------------------------------------------

def get_ai_response(prompt: str) -> str:
    try:
        llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
        response_content = llm.invoke(prompt).content
        if isinstance(response_content, list):
            text_parts = []
            for item in response_content:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            response = "".join(text_parts)
        else:
            response = str(response_content)
            
        if not response.strip():
            return "⚠️ I couldn't generate a response. Please try rephrasing your prompt."
        return response
    except Exception as exc:
        raise RuntimeError(f"NVIDIA API Error: {exc}")


def append_image_recall(answer, user, query):
    if '![' in answer:
        return answer
    matched = find_matching_images(user, query)
    if not matched:
        return answer
    markdown = format_image_recall_markdown(matched)
    intro = "Here are the matching images from your memory gallery:"
    if answer.strip():
        return f"{answer.rstrip()}\n\n{intro}\n\n{markdown}"
    return f"{intro}\n\n{markdown}"


def sanitize_chat_content(content: str) -> str:
    def replace(match):
        alt_text = match.group(1) or 'image'
        url = match.group(2)
        file_name = None
        if url.startswith('/api/media/serve/'):
            file_name = url.split('/api/media/serve/', 1)[1]
        elif url.startswith('/media/'):
            file_name = url.split('/media/', 1)[1]

        if file_name is not None and not DatabaseFile.objects.filter(name=file_name).exists():
            return f"[Deleted image: {alt_text}]"
        return match.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace, content)


def stream_general_chat(session, prompt):
    try:
        past_messages = list(session.messages.order_by('-timestamp').only('role', 'content')[:20])
        past_messages.reverse()
        ChatMessage.objects.create(session=session, role='user', content=prompt)
        
        history_parts = []
        for msg in past_messages:
            prefix = "Human" if msg.role == 'user' else "Assistant"
            history_parts.append(f"{prefix}: {msg.content}")
        history_text = "\n".join(history_parts)
        
        img_context = get_image_context(session.user, prompt)
        full_prompt = f"{history_text}\nHuman: {prompt}\nAssistant:" if history_text else f"Human: {prompt}\nAssistant:"
        if img_context:
            full_prompt = f"{img_context}\n\n{full_prompt}"

        llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
        
        full_response = ""
        for chunk in llm.stream(full_prompt):
            if chunk and chunk.content:
                text = chunk.content
                if isinstance(text, list):
                    text_parts = []
                    for item in text:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                        elif isinstance(item, str):
                            text_parts.append(item)
                    text = "".join(text_parts)
                else:
                    text = str(text)
                
                full_response += text
                yield f"data: {json.dumps({'chunk': text, 'session_id': session.id, 'session_title': session.title})}\n\n"
                
        sanitized_response = sanitize_chat_content(
            append_image_recall(full_response, session.user, prompt)
        )
        if len(sanitized_response) > len(full_response):
            extra = sanitized_response[len(full_response):]
            yield f"data: {json.dumps({'chunk': extra, 'session_id': session.id, 'session_title': session.title})}\n\n"
            
        ChatMessage.objects.create(session=session, role='bot', content=sanitized_response)
        yield f"data: {json.dumps({'done': True})}\n\n"
        
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"

# --- HTML Template Views ---

def dashboard_view(request):
    # Anonymous visitors get the public marketing landing page;
    # authenticated users get their workspace dashboard.
    if not request.user.is_authenticated:
        return render(request, 'landing.html')
    return render(request, 'dashboard.html')

@login_required
def chat_view(request):
    return render(request, 'chat.html')

@login_required
def tasks_view(request):
    return render(request, 'tasks.html')

@login_required
def expenses_view(request):
    return render(request, 'expenses.html')

@login_required
def general_chat_view(request):
    return render(request, 'general_chat.html')

@login_required
def image_gen_view(request):
    return render(request, 'image_gen.html')

def register_view(request):
    if request.method == 'POST':
        uname = request.POST.get('username')
        upass = request.POST.get('password')
        email = request.POST.get('email')
        phone = request.POST.get('phone_number')
        if uname and upass and email and phone:
            if User.objects.filter(username=uname).exists():
                return render(request, 'registration/register.html', {'error': 'Username already exists'})
            user = User.objects.create_user(username=uname, password=upass, email=email)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone_number = phone
            profile.save()
            login(request, user)
            return redirect('/')
    return render(request, 'registration/register.html')

def logout_view(request):
    """Custom logout view — works reliably across all Django 5+/6.x versions."""
    if request.method == 'POST':
        auth_logout(request)
        return redirect('login')
    # Fallback for GET: redirect to login
    return redirect('login')



@login_required
def about_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            profile.profile_picture = request.FILES['profile_picture']
            profile.save()
            return redirect('about')
        
        # Handle profile details update
        email = request.POST.get('email')
        phone = request.POST.get('phone_number')
        
        if email is not None:
            request.user.email = email
            request.user.save()
        if phone is not None:
            profile.phone_number = phone
            profile.save()
            
        return redirect('about')
        
    return render(request, 'about.html')


# --- API Views (DRF) ---

class UploadNotesView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': 'No files provided'}, status=400)

        text_count = 0
        img_count = 0

        from django.core.files.storage import Storage
        from django.core.files.base import ContentFile
        from api.storage import DatabaseStorage

        storage = DatabaseStorage()

        for f in files:
            name_lower = f.name.lower()
            if name_lower.endswith(('.jpg', '.jpeg', '.png')):
                img_mem = ImageMemory(
                    user=request.user,
                    image=f,
                    filename=f.name
                )
                img_mem.save()
                
                # Extract EXIF metadata
                meta = extract_exif_metadata(img_mem.image)
                if meta['captured_at']:
                    img_mem.captured_at = meta['captured_at']
                if meta['camera_model']:
                    img_mem.camera_model = meta['camera_model']
                if meta['location']:
                    img_mem.location = meta['location']
                
                img_mem.save()
                img_count += 1
            else:
                file_name = f"user_{request.user.id}/{f.name}"
                if storage.exists(file_name):
                    storage.delete(file_name)
                stored_name = storage.save(file_name, ContentFile(f.read()))
                print(f"Saved note: {stored_name}")
                text_count += 1

        if text_count > 0:
            invalidate_aggregate_notes_cache(request.user.id)
            import threading
            threading.Thread(target=retrain_vector_db, args=(request.user.id,), daemon=True).start()

        return Response({'message': f'Successfully uploaded {text_count} documents and {img_count} images.'})


class RetrainDBView(APIView):
    def post(self, request):
        try:
            retrain_vector_db(request.user.id)
            return Response({'message': 'Vector DB retrained successfully'})
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get('query')
        session_id = request.data.get('session_id')
        selected_notes = request.data.get('selected_notes', [])
        
        if not query:
            return Response({'error': 'No query provided'}, status=400)

        # Get or create session
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return Response({'error': 'Session not found'}, status=404)
        else:
            title = query[:60] + ('...' if len(query) > 60 else '')
            session = ChatSession.objects.create(user=request.user, title=title, chat_type='notes')

        # Build a bounded conversation history for context and avoid oversized prompts
        past_messages = list(session.messages.order_by('-timestamp').only('role', 'content')[:20])
        past_messages.reverse()

        # Save user message
        ChatMessage.objects.create(session=session, role='user', content=query)

        history_text = ""
        for msg in past_messages:
            prefix = "User" if msg.role == 'user' else "Assistant"
            history_text += f"{prefix}: {msg.content}\n"

        try:
            qa_chain = get_qa_chain(request.user.id)
            # Inject history into the query
            full_query = f"{history_text}User: {query}" if history_text else query
            
            # Fetch matching image context
            img_context = get_image_context(request.user, query)
            
            answer = qa_chain.run(full_query, selected_notes=selected_notes, image_context=img_context)
        except Exception as e:
            answer = f"Error: {str(e)}"

        answer = append_image_recall(answer, request.user, query)
        answer = sanitize_chat_content(answer)

        # Save bot response
        ChatMessage.objects.create(session=session, role='bot', content=answer)

        return Response({'answer': answer, 'session_id': session.id, 'session_title': session.title})


class NotesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from api.models import DatabaseFile
        prefix = f"user_{request.user.id}/"
        db_files = DatabaseFile.objects.filter(name__startswith=prefix)
        notes = []
        for db_file in db_files:
            if db_file.name.endswith(('.md', '.txt')):
                display_name = db_file.name.replace(prefix, "") if db_file.name.startswith(prefix) else db_file.name
                if display_name not in notes:
                    notes.append(display_name)

        if not notes:
            notes_dir = Path(settings.BASE_DIR) / 'notes'
            if notes_dir.exists():
                for ext in ("**/*.md", "**/*.txt"):
                    for file in notes_dir.glob(ext):
                        if file.is_file():
                            if file.name not in notes:
                                notes.append(file.name)

        return Response({'notes': sorted(notes)})


class GeneralChatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        prompt = request.data.get('prompt')
        session_id = request.data.get('session_id')
        if not prompt:
            return Response({'error': 'No prompt provided'}, status=400)

        # Get or create session
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return Response({'error': 'Session not found'}, status=404)
        else:
            title = prompt[:60] + ('...' if len(prompt) > 60 else '')
            session = ChatSession.objects.create(user=request.user, title=title, chat_type='general')

        return StreamingHttpResponse(
            stream_general_chat(session, prompt),
            content_type='text/event-stream'
        )


class ImageGenerationAPIView(APIView):
    def post(self, request):
        prompt = request.data.get('prompt')
        if not prompt:
            return Response({'error': 'No prompt provided'}, status=400)
            
        model_choice = request.data.get('model', 'flux_schnell')
        hf_token = os.environ.get("HF_TOKEN")
        
        if not hf_token:
            return Response({'error': 'Hugging Face API token (HF_TOKEN) is not configured in the server environment.'}, status=500)
            
        # Define priority list of models to try. FLUX.1-schnell is verified working on this system.
        if model_choice == 'sdxl_base':
            models_to_try = [
                "stabilityai/stable-diffusion-xl-base-1.0",
                "black-forest-labs/FLUX.1-schnell",
                "runwayml/stable-diffusion-v1-5"
            ]
        elif model_choice == 'sd_15':
            models_to_try = [
                "runwayml/stable-diffusion-v1-5",
                "black-forest-labs/FLUX.1-schnell"
            ]
        else: # flux_schnell (default)
            models_to_try = [
                "black-forest-labs/FLUX.1-schnell",
                "runwayml/stable-diffusion-v1-5"
            ]
            
        # Try each model in sequence until one succeeds and returns valid image data
        for model_id in models_to_try:
            try:
                # Use the new Hugging Face serverless router endpoint
                model_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
                headers = {"Authorization": f"Bearer {hf_token}"}
                payload = {
                    "inputs": prompt,
                    "options": {"wait_for_model": True}
                }
                
                print(f"Attempting image generation using model: {model_id}...")
                response = requests.post(model_url, headers=headers, json=payload, timeout=60)
                
                # Check status and verify PNG/JPEG magic bytes
                is_valid_image = response.status_code == 200 and (response.content.startswith(b'\x89PNG') or response.content.startswith(b'\xff\xd8'))
                
                if is_valid_image:
                    filename = f"generated/{uuid.uuid4()}.png"
                    from django.core.files.storage import default_storage
                    from django.core.files.base import ContentFile
                    default_storage.save(filename, ContentFile(response.content))
                    
                    image_url = default_storage.url(filename)
                    is_fallback = (model_id != models_to_try[0])
                    return Response({
                        'image_url': image_url,
                        'model_used': model_id,
                        'fallback': is_fallback
                    })
                else:
                    print(f"HF model {model_id} returned invalid response (code {response.status_code}). Trying fallback...")
            except Exception as e:
                print(f"Error calling HF model {model_id}: {e}. Trying fallback...")
                
        return Response({'error': 'Image generation failed on all available models. Please verify your Hugging Face API key status and model accessibility.'}, status=500)


class ChatSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        chat_type = request.query_params.get('type', 'general')
        sessions = ChatSession.objects.filter(
            user=request.user, chat_type=chat_type
        ).annotate(message_count=Count('messages')).order_by('-created_at')
        from .serializers import ChatSessionSummarySerializer
        serializer = ChatSessionSummarySerializer(sessions, many=True)
        return Response({'sessions': serializer.data})

    def delete(self, request):
        session_id = request.query_params.get('id')
        if session_id:
            ChatSession.objects.filter(id=session_id, user=request.user).delete()
            return Response({'message': 'Session deleted'})
        return Response({'error': 'No session id provided'}, status=400)


class ChatSessionMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)
        messages = session.messages.order_by('timestamp')
        serializer = ChatMessageSerializer(messages, many=True)

        sanitized_messages = []
        for msg_obj, msg_data in zip(messages, serializer.data):
            msg_data['content'] = sanitize_chat_content(msg_obj.content)
            sanitized_messages.append(msg_data)

        return Response({'messages': sanitized_messages, 'title': session.title})


class TasksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        all_tasks, _ = aggregate_notes(user_id=request.user.id)
        serializer = TaskSerializer(all_tasks, many=True)
        return Response({'tasks': serializer.data})

    def post(self, request):
        action = request.data.get('action') # 'add' or 'complete'
        
        if action == 'add':
            task_text = request.data.get('task')
            if not task_text:
                return Response({'error': 'Task description is required'}, status=400)
            
            task_date = request.data.get('date')
            if not task_date:
                from datetime import date
                task_date = date.today().strftime('%Y-%m-%d')
            
            file_name = f"user_{request.user.id}/{task_date}.md"
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            content = ""
            if default_storage.exists(file_name):
                with default_storage.open(file_name, 'rb') as f:
                    content = f.read().decode('utf-8')
            else:
                content = f"# Notes for {task_date}\n"
            
            if content and not content.endswith('\n'):
                content += '\n'
            content += f"- [ ] {task_text}\n"
            
            if default_storage.exists(file_name):
                default_storage.delete(file_name)
            default_storage.save(file_name, ContentFile(content.encode('utf-8')))
            
            invalidate_aggregate_notes_cache(request.user.id)
            import threading
            threading.Thread(target=retrain_vector_db, args=(request.user.id,), daemon=True).start()
            
            return Response({'message': 'Task added successfully', 'date': task_date})
            
        elif action == 'complete':
            task_text = request.data.get('task')
            if not task_text:
                return Response({'error': 'Task description is required'}, status=400)
            
            task_date = request.data.get('date')
            
            from api.models import DatabaseFile
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            found = False
            files_to_check = []
            prefix = f"user_{request.user.id}/"
            if task_date and task_date != 'N/A' and task_date != 'None':
                target_file_md = f"{prefix}{task_date}.md"
                target_file_txt = f"{prefix}{task_date}.txt"
                if DatabaseFile.objects.filter(name=target_file_md).exists():
                    files_to_check.append(target_file_md)
                if DatabaseFile.objects.filter(name=target_file_txt).exists():
                    files_to_check.append(target_file_txt)
            
            # Always append all other files as fallback
            db_files = DatabaseFile.objects.filter(name__startswith=prefix)
            for db_file in db_files:
                if db_file.name.endswith(('.md', '.txt')):
                    if db_file.name not in files_to_check:
                        files_to_check.append(db_file.name)

            import re
            for file_name in files_to_check:
                with default_storage.open(file_name, 'rb') as f:
                    content = f.read().decode('utf-8')
                content = content.lstrip('\ufeff')

                lines = content.splitlines(keepends=True)
                
                modified = False
                inside_tasks = False
                
                for i, line in enumerate(lines):
                    line_strip = line.strip()
                    # Check for section headers
                    header_match = re.match(r"^(#+)\s*(.+)$", line_strip)
                    if header_match:
                        header_title = header_match.group(2).strip().lower()
                        if any(k in header_title for k in ["task", "todo", "to-do", "to do", "action item"]):
                            inside_tasks = True
                        else:
                            inside_tasks = False
                        continue

                    # A. Checkbox Match (- [ ] task or - [x] task)
                    cb_match = re.match(r"^(\s*[-*]?\s*\[\s*[ xX]?\s*\]\s*)(.+)$", line)
                    if cb_match:
                        existing_task = cb_match.group(2).strip()
                        if existing_task.lower() == task_text.lower():
                            lines[i] = re.sub(r"\[\s*[ xX]?\s*\]|\[\]", "[x]", line, count=1)
                            modified = True
                            found = True
                            break
                        # Don't skip - fall through to check other patterns on same line

                    # B. Prefix label Match: todo: ..., task: ..., action: ...
                    if not found:
                        pref_match = re.match(r"^(\s*[-*]?\s*)(?:todo|task|action|to-do)\s*:\s*(.+)$", line, re.IGNORECASE)
                        if pref_match:
                            existing_task = pref_match.group(2).strip()
                            if existing_task.lower() == task_text.lower():
                                bullet = pref_match.group(1) if pref_match.group(1).strip() else "- "
                                lines[i] = f"{bullet}[x] {pref_match.group(2)}\n"
                                modified = True
                                found = True
                                break

                    # C. Simple Bullet under Tasks/Todo header
                    if not found and inside_tasks:
                        bullet_match = re.match(r"^(\s*[-*]\s*)(.+)$", line)
                        if bullet_match:
                            existing_task = bullet_match.group(2).strip()
                            if existing_task.lower() == task_text.lower():
                                lines[i] = f"{bullet_match.group(1)}[x] {bullet_match.group(2)}\n"
                                modified = True
                                found = True
                                break

                if not modified:
                    # Fuzzy fallback: find the line that contains task_text (case-insensitive)
                    for i, line in enumerate(lines):
                        line_strip = line.strip()
                        if not line_strip or line_strip.startswith('#'):
                            continue
                        if task_text.lower() in line_strip.lower():
                            # Replace any unchecked checkbox marker
                            if re.search(r"\[\s*[ ]?\s*\]|\[\]", line):
                                lines[i] = re.sub(r"\[\s*[ ]?\s*\]|\[\]", "[x]", line, count=1)
                            else:
                                # Convert bullet to checkbox
                                bm = re.match(r"^(\s*[-*]\s*)(.+)$", line)
                                if bm:
                                    lines[i] = f"{bm.group(1)}[x] {bm.group(2)}\n"
                                else:
                                    lines[i] = f"[x] {line_strip}\n"
                            modified = True
                            found = True
                            break
                
                if modified:
                    new_content = "".join(lines)
                    default_storage.delete(file_name)
                    default_storage.save(file_name, ContentFile(new_content.encode('utf-8')))
                    break
            
            if found:
                invalidate_aggregate_notes_cache(request.user.id)
                import threading
                threading.Thread(target=retrain_vector_db, args=(request.user.id,), daemon=True).start()
                return Response({'message': 'Task marked as done'})
            else:
                return Response({'error': 'Task not found in notes'}, status=404)
        
        else:
            return Response({'error': 'Invalid action'}, status=400)


class ExpensesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, all_expenses = aggregate_notes(user_id=request.user.id)
        serializer = ExpenseSerializer(all_expenses, many=True)
        return Response({'expenses': serializer.data})

    def post(self, request):
        action = request.data.get('action', 'add')
        
        if action == 'delete':
            category = request.data.get('category')
            amount = request.data.get('amount')
            expense_date = request.data.get('date')
            
            if not category:
                return Response({'error': 'Category is required'}, status=400)
            if amount is None or amount == '':
                return Response({'error': 'Amount is required'}, status=400)
            
            try:
                amount_val = float(amount)
            except ValueError:
                return Response({'error': 'Amount must be a valid number'}, status=400)
                
            from api.models import DatabaseFile
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            files_to_check = []
            prefix = f"user_{request.user.id}/"
            if expense_date and expense_date != 'N/A' and expense_date != 'None':
                target_file = f"{prefix}{expense_date}.md"
                if DatabaseFile.objects.filter(name=target_file).exists():
                    files_to_check.append(target_file)
            
            if not files_to_check:
                db_files = DatabaseFile.objects.filter(name__startswith=prefix)
                for db_file in db_files:
                    if db_file.name.endswith('.md'):
                        files_to_check.append(db_file.name)
                        
            import re
            found = False
            for file_name in files_to_check:
                with default_storage.open(file_name, 'rb') as f:
                    content = f.read().decode('utf-8')
                lines = content.splitlines(keepends=True)
                
                new_lines = []
                modified = False
                for line in lines:
                    if not modified and category.lower() in line.lower():
                        numbers = re.findall(r"\d+(?:\.\d+)?", line.replace(",", ""))
                        if any(float(num) == amount_val for num in numbers):
                            modified = True
                            found = True
                            continue
                    new_lines.append(line)
                
                if modified:
                    new_content = "".join(new_lines)
                    default_storage.delete(file_name)
                    default_storage.save(file_name, ContentFile(new_content.encode('utf-8')))
                    break
                    
            if found:
                import threading
                threading.Thread(target=retrain_vector_db, args=(request.user.id,)).start()
                return Response({'message': 'Expense deleted successfully'})
            else:
                return Response({'error': 'Expense not found in notes'}, status=404)
        
        # Add action (default)
        category = request.data.get('category')
        amount = request.data.get('amount')
        
        if not category:
            return Response({'error': 'Category is required'}, status=400)
        if amount is None or amount == '':
            return Response({'error': 'Amount is required'}, status=400)
        
        try:
            amount_val = float(amount)
        except ValueError:
            return Response({'error': 'Amount must be a valid number'}, status=400)
            
        expense_date = request.data.get('date')
        if not expense_date:
            from datetime import date
            expense_date = date.today().strftime('%Y-%m-%d')
            
        file_name = f"user_{request.user.id}/{expense_date}.md"
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        
        content = ""
        if default_storage.exists(file_name):
            with default_storage.open(file_name, 'rb') as f:
                content = f.read().decode('utf-8')
        else:
            content = f"# Notes for {expense_date}\n"
            
        if content and not content.endswith('\n'):
            content += '\n'
        content += f"- ₹{amount_val} - {category}\n"
        
        if default_storage.exists(file_name):
            default_storage.delete(file_name)
        default_storage.save(file_name, ContentFile(content.encode('utf-8')))
            
        invalidate_aggregate_notes_cache(request.user.id)
        import threading
        threading.Thread(target=retrain_vector_db, args=(request.user.id,), daemon=True).start()
        
        return Response({'message': 'Expense added successfully', 'date': expense_date})


class OllamaStatusView(APIView):
    def get(self, request):
        return Response({'running': True, 'message': 'NVIDIA API Active'})


# --- Gallery Views & API ---

@login_required
def gallery_view(request):
    return render(request, 'gallery.html')


class GalleryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request):
        search_query = request.query_params.get('search', '').strip()
        memories = ImageMemory.objects.filter(user=request.user)
        
        if search_query:
            memories = memories.filter(
                Q(description__icontains=search_query) |
                Q(location__icontains=search_query) |
                Q(tags__icontains=search_query) |
                Q(filename__icontains=search_query) |
                Q(camera_model__icontains=search_query)
            )
            
        memories = memories.order_by('-uploaded_at')
        
        data = []
        for m in memories:
            data.append({
                'id': m.id,
                'url': m.image.url,
                'filename': m.filename,
                'description': m.description,
                'tags': m.tags,
                'location': m.location,
                'captured_at': m.captured_at.strftime('%Y-%m-%d %H:%M:%S') if m.captured_at else None,
                'camera_model': m.camera_model,
                'uploaded_at': m.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        return Response({'memories': data})

    def post(self, request):
        memory_id = request.data.get('id')
        if memory_id:
            try:
                memory = ImageMemory.objects.get(id=memory_id, user=request.user)
            except ImageMemory.DoesNotExist:
                return Response({'error': 'Memory not found'}, status=404)
            
            description = request.data.get('description')
            tags = request.data.get('tags')
            location = request.data.get('location')
            captured_at_str = request.data.get('captured_at')
            camera_model = request.data.get('camera_model')
            
            if description is not None:
                memory.description = description
            if tags is not None:
                memory.tags = tags
            if location is not None:
                memory.location = location
            if camera_model is not None:
                memory.camera_model = camera_model
            if captured_at_str is not None:
                if captured_at_str == '':
                    memory.captured_at = None
                else:
                    try:
                        try:
                            memory.captured_at = datetime.strptime(captured_at_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            memory.captured_at = datetime.strptime(captured_at_str, "%Y-%m-%d")
                    except ValueError:
                        return Response({'error': 'Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS'}, status=400)
            
            memory.save()
            return Response({'message': 'Memory updated successfully', 'id': memory.id})
        else:
            files = request.FILES.getlist('files')
            if not files:
                file_obj = request.FILES.get('file')
                if file_obj:
                    files = [file_obj]
                else:
                    return Response({'error': 'No image file provided'}, status=400)
            
            created_count = 0
            new_memories = []
            for f in files:
                name_lower = f.name.lower()
                if not name_lower.endswith(('.jpg', '.jpeg', '.png')):
                    continue
                
                img_mem = ImageMemory(
                    user=request.user,
                    image=f,
                    filename=f.name
                )
                img_mem.save()
                
                meta = extract_exif_metadata(img_mem.image)
                if meta['captured_at']:
                    img_mem.captured_at = meta['captured_at']
                if meta['camera_model']:
                    img_mem.camera_model = meta['camera_model']
                if meta['location']:
                    img_mem.location = meta['location']
                
                desc = request.data.get('description', '')
                tags = request.data.get('tags', '').strip()
                if desc:
                    img_mem.description = desc
                if not tags and desc:
                    tags = ', '.join(extract_keywords_from_text(desc))
                if tags:
                    img_mem.tags = tags
                
                img_mem.save()
                created_count += 1
                new_memories.append({
                    'id': img_mem.id,
                    'url': img_mem.image.url,
                    'filename': img_mem.filename,
                    'description': img_mem.description,
                    'tags': img_mem.tags,
                    'location': img_mem.location,
                    'captured_at': img_mem.captured_at.strftime('%Y-%m-%d %H:%M:%S') if img_mem.captured_at else None,
                    'camera_model': img_mem.camera_model,
                    'uploaded_at': img_mem.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
                })
                
            return Response({
                'created': created_count,
                'message': f'Successfully uploaded {created_count} images.',
                'memories': new_memories
            })

    def delete(self, request):
        memory_id = request.query_params.get('id')
        if not memory_id:
            memory_id = request.data.get('id')
            
        if not memory_id:
            return Response({'error': 'No memory id provided'}, status=400)
            
        try:
            memory = ImageMemory.objects.get(id=memory_id, user=request.user)
            memory.delete()
            invalidate_aggregate_notes_cache(request.user.id)
            return Response({'message': 'Memory deleted successfully'})
        except ImageMemory.DoesNotExist:
            return Response({'error': 'Memory not found'}, status=404)


from django.http import HttpResponse, Http404

def serve_media_view(request, filename):
    from .models import DatabaseFile
    filename = filename.replace('\\', '/')
    try:
        db_file = DatabaseFile.objects.get(name=filename)
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = 'application/octet-stream'
        response = HttpResponse(db_file.content, content_type=content_type)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
    except DatabaseFile.DoesNotExist:
        raise Http404("File not found")

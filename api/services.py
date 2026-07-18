import os
import shutil
import threading
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from django.conf import settings

from parsers import aggregate_notes, parse_tasks_and_expenses

retrain_lock = threading.Lock()
embedding_lock = threading.Lock()
_embedding_model = None

def get_db_connection_string():
    supabase_host = os.environ.get("SUPABASE_DB_HOST")
    if not supabase_host:
        return None

    # If a full URL is provided, normalize it and quote credentials.
    if supabase_host.startswith("postgresql://") or supabase_host.startswith("postgres://"):
        parsed = urlparse(supabase_host)
        scheme = parsed.scheme
        if scheme == "postgres":
            scheme = "postgresql+psycopg2"
        else:
            scheme = "postgresql+psycopg2" if not scheme.startswith("postgresql+") else scheme

        username = quote_plus(parsed.username) if parsed.username else quote_plus(os.environ.get("SUPABASE_DB_USER", "postgres"))
        password = quote_plus(parsed.password) if parsed.password else quote_plus(os.environ.get("SUPABASE_DB_PASSWORD", ""))
        host = parsed.hostname or os.environ.get("SUPABASE_DB_HOST")
        port = parsed.port or int(os.environ.get("SUPABASE_DB_PORT", "5432"))
        dbname = parsed.path.lstrip("/") or os.environ.get("SUPABASE_DB_NAME", "postgres")
        return f"{scheme}://{username}:{password}@{host}:{port}/{dbname}"

    supabase_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    supabase_user = quote_plus(os.environ.get("SUPABASE_DB_USER", "postgres"))
    supabase_pass = quote_plus(os.environ.get("SUPABASE_DB_PASSWORD", ""))
    supabase_port = os.environ.get("SUPABASE_DB_PORT", "5432")

    return f"postgresql+psycopg2://{supabase_user}:{supabase_pass}@{supabase_host}:{supabase_port}/{supabase_name}"

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with embedding_lock:
            if _embedding_model is None:
                import torch
                torch.set_num_threads(1)
                torch.set_num_interop_threads(1)
                from langchain_community.embeddings import HuggingFaceEmbeddings
                _embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return _embedding_model

def retrain_vector_db(user_id):
    with retrain_lock:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import PGVector
        
        connection_string = get_db_connection_string()
        if not connection_string:
            print("SUPABASE_DB_HOST not configured. Cannot save vectors to Supabase Vector store.")
            return
            
        collection_name = f"user_{user_id}_collection"
        embedding_model = get_embedding_model()
        
        from api.models import DatabaseFile
        from langchain_core.documents import Document
        
        docs = []
        prefix = f"user_{user_id}/"
        db_files = DatabaseFile.objects.filter(name__startswith=prefix)
        for db_file in db_files:
            if db_file.name.endswith(('.md', '.txt')):
                try:
                    content_str = bytes(db_file.content).decode('utf-8')
                    docs.append(Document(
                        page_content=content_str,
                        metadata={"source": db_file.name}
                    ))
                except Exception as e:
                    print(f"Error decoding file {db_file.name}: {e}")
        
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(docs)
        
        # If there are no chunks, delete existing collection
        if not chunks:
            try:
                store = PGVector(
                    connection_string=connection_string,
                    embedding_function=embedding_model,
                    collection_name=collection_name
                )
                store.delete_collection()
            except Exception as e:
                print(f"Error deleting collection: {e}")
            return

        # Initialize/Re-create collection with chunks, deleting the old one first
        try:
            vectordb = PGVector.from_documents(
                documents=chunks,
                embedding=embedding_model,
                collection_name=collection_name,
                connection_string=connection_string,
                pre_delete_collection=True
            )
        except Exception as e:
            print(f"Error saving to PGVector: {e}")

def _is_task_query(query):
    q = query.lower()
    return any(k in q for k in ('task', 'todo', 'to-do', 'action item', 'action items'))


def _is_expense_query(query):
    q = query.lower()
    return any(
        k in q for k in (
            'expense', 'expenses', 'finance', 'spending', 'budget',
            'cost', 'paid', 'spent', 'money', 'invoice',
        )
    )


def _is_summary_query(query):
    q = query.lower()
    return any(k in q for k in ('summarize', 'summary', 'overview', 'list my', 'what are my'))


def _format_tasks_expenses_summary(tasks, expenses, query):
    q_lower = query.lower()
    want_tasks = _is_task_query(query) or _is_summary_query(query)
    want_expenses = _is_expense_query(query) or _is_summary_query(query)

    if not want_tasks and not want_expenses:
        want_tasks = bool(tasks)
        want_expenses = bool(expenses)

    parts = []
    if want_tasks and tasks:
        parts.append("Tasks:")
        for task in tasks:
            status = task.get('status', 'todo')
            marker = 'x' if status == 'done' else ' '
            date_str = f" ({task['date']})" if task.get('date') else ''
            parts.append(f"- [{marker}] {task.get('task', '')}{date_str}")

    if want_expenses and expenses:
        parts.append("Expenses:")
        for expense in expenses:
            date_str = f" ({expense['date']})" if expense.get('date') else ''
            amount = expense.get('amount', '')
            # Format amount with ₹ prefix and clean up float display
            try:
                amount_str = f"\u20b9{amount:,.2f}".rstrip('0').rstrip('.')
            except (TypeError, ValueError):
                amount_str = f"\u20b9{amount}"
            parts.append(f"- {expense.get('category', '')}: {amount_str}{date_str}")

    return "\n".join(parts) if parts else None


def _notes_fallback_response(user_id, query, image_context=None):
    all_tasks, all_expenses = aggregate_notes(user_id=user_id)
    summary = _format_tasks_expenses_summary(all_tasks, all_expenses, query)

    if summary and (_is_task_query(query) or _is_expense_query(query) or _is_summary_query(query)):
        return summary

    if summary and not image_context:
        return summary

    if image_context:
        return None

    if all_tasks or all_expenses:
        return _format_tasks_expenses_summary(all_tasks, all_expenses, query)

    return (
        "I couldn't find any relevant information in your notes. "
        "Upload .md/.txt files from the dashboard, then ask again."
    )


def get_qa_chain(user_id):
    class CustomQAChain:
        def run(self, query, selected_notes=None, image_context=None):
            from langchain_community.vectorstores import PGVector
            from langchain_nvidia_ai_endpoints import ChatNVIDIA

            if _is_summary_query(query):
                from api.models import DatabaseFile
                prefix = f"user_{user_id}/"
                note_contents = []
                if selected_notes and isinstance(selected_notes, list) and len(selected_notes) > 0:
                    for note in selected_notes:
                        note_name = f"{prefix}{note}"
                        try:
                            db_file = DatabaseFile.objects.get(name=note_name)
                            content_str = bytes(db_file.content).decode('utf-8')
                            note_contents.append(f"--- Note: {note} ---\n{content_str}")
                        except DatabaseFile.DoesNotExist:
                            pass
                if not note_contents:
                    db_files = DatabaseFile.objects.filter(name__startswith=prefix)
                    for db_file in db_files:
                        if db_file.name.endswith(('.md', '.txt')):
                            try:
                                content_str = bytes(db_file.content).decode('utf-8')
                                display_name = db_file.name.replace(prefix, "")
                                note_contents.append(f"--- Note: {display_name} ---\n{content_str}")
                            except Exception:
                                pass
                if note_contents:
                    notes_text = "\n\n".join(note_contents)
                    try:
                        llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
                        summary_prompt = (
                            f"You are a personal assistant. The user wants a summary of their notes.\n\n"
                            f"Here is the text content of the notes:\n\n"
                            f"{notes_text}\n\n"
                            f"Please provide a cohesive, clear, and comprehensive natural language summary of the note contents. "
                            f"Summarize the main points, tasks, and budget/spending info in professional, detailed paragraphs."
                        )
                        response_content = llm.invoke(summary_prompt).content
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
                        if response.strip():
                            return response
                    except Exception:
                        pass

            if _is_task_query(query) or _is_expense_query(query):
                all_tasks, all_expenses = aggregate_notes(user_id=user_id)
                structured_data = _format_tasks_expenses_summary(all_tasks, all_expenses, query)
                if structured_data and not image_context:
                    # Route through LLM for a natural language response
                    try:
                        llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct")
                        summary_prompt = (
                            f"You are a personal assistant. The user asked: \"{query}\"\n\n"
                            f"Here is the structured data extracted from their notes:\n\n"
                            f"{structured_data}\n\n"
                            f"Please provide a clear, concise, and friendly natural language "
                            f"response. Include totals where relevant for expenses. "
                            f"Format nicely using markdown where helpful."
                        )
                        response_content = llm.invoke(summary_prompt).content
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
                        if response.strip():
                            return response
                        return structured_data  # fallback if LLM returns empty
                    except Exception:
                        return structured_data  # fallback to raw structured data


            connection_string = get_db_connection_string()
            if not connection_string:
                fallback = _notes_fallback_response(user_id, query, image_context=image_context)
                if fallback:
                    return fallback
                if image_context:
                    return "Here are the matching images from your memory gallery."
                return "I don't have any database configuration set up for vector recall yet."

            collection_name = f"user_{user_id}_collection"
            vectordb = None
            try:
                embedding_model = get_embedding_model()
                vectordb = PGVector(
                    connection_string=connection_string,
                    embedding_function=embedding_model,
                    collection_name=collection_name
                )
            except Exception:
                vectordb = None

            filter_kwargs = None
            if selected_notes and isinstance(selected_notes, list) and len(selected_notes) > 0:
                relative_paths = [f"user_{user_id}/{note}" for note in selected_notes]
                if len(relative_paths) == 1:
                    filter_kwargs = {"source": {"$eq": relative_paths[0]}}
                else:
                    filter_kwargs = {"source": {"$in": relative_paths}}

            docs = []
            if vectordb is not None:
                try:
                    if filter_kwargs:
                        docs = vectordb.similarity_search(query, k=3, filter=filter_kwargs)
                        if not docs:
                            docs = vectordb.similarity_search(query, k=3)
                    else:
                        docs = vectordb.similarity_search(query, k=3)
                except Exception:
                    docs = []

            if not docs:
                fallback = _notes_fallback_response(user_id, query, image_context=image_context)
                if fallback:
                    return fallback
                if image_context:
                    return "Here are the matching images from your memory gallery."

            context = "\n".join([doc.page_content for doc in docs])
            prompt = (
                "Use the following context to answer the question. "
                "If matched images are provided, include them in markdown image format.\n\n"
                f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
            )
            if image_context:
                prompt = f"{image_context}\n\n{prompt}"

            try:
                llm = ChatNVIDIA(
                    model="meta/llama-3.1-8b-instruct"
                )
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
                fallback = _notes_fallback_response(user_id, query, image_context=image_context)
                if fallback:
                    return fallback
                return f"NVIDIA API Error: {exc}"
    return CustomQAChain()

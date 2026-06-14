import os
import shutil
import threading
from django.conf import settings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_nvidia_ai_endpoints import ChatNVIDIA

retrain_lock = threading.Lock()

def get_db_connection_string():
    supabase_host = os.environ.get("SUPABASE_DB_HOST")
    if not supabase_host:
        return None
    supabase_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    supabase_user = os.environ.get("SUPABASE_DB_USER", "postgres")
    supabase_pass = os.environ.get("SUPABASE_DB_PASSWORD", "")
    supabase_port = os.environ.get("SUPABASE_DB_PORT", "5432")
    return f"postgresql+psycopg2://{supabase_user}:{supabase_pass}@{supabase_host}:{supabase_port}/{supabase_name}"

def retrain_vector_db(user_id):
    with retrain_lock:
        connection_string = get_db_connection_string()
        if not connection_string:
            print("SUPABASE_DB_HOST not configured. Cannot save vectors to Supabase Vector store.")
            return
            
        collection_name = f"user_{user_id}_collection"
        embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        from api.models import DatabaseFile
        from langchain_core.documents import Document
        
        docs = []
        prefix = f"user_{user_id}/"
        db_files = DatabaseFile.objects.filter(name__startswith=prefix)
        for db_file in db_files:
            if db_file.name.endswith(('.md', '.txt')):
                try:
                    content_str = db_file.content.decode('utf-8')
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

def get_qa_chain(user_id):
    class CustomQAChain:
        def run(self, query, selected_notes=None, image_context=None):
            connection_string = get_db_connection_string()
            if not connection_string:
                 return "I don't have any database configuration set up for vector recall yet."
                 
            collection_name = f"user_{user_id}_collection"
            embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            
            try:
                vectordb = PGVector(
                    connection_string=connection_string,
                    embedding_function=embedding_model,
                    collection_name=collection_name
                )
            except Exception as e:
                return f"Failed to connect to Supabase Vector store: {e}"
            
            filter_kwargs = None
            if selected_notes and isinstance(selected_notes, list) and len(selected_notes) > 0:
                relative_paths = [f"user_{user_id}/{note}" for note in selected_notes]
                if len(relative_paths) == 1:
                    filter_kwargs = {"source": {"$eq": relative_paths[0]}}
                else:
                    filter_kwargs = {"source": {"$in": relative_paths}}
            
            try:
                docs = vectordb.similarity_search(query, k=3, filter=filter_kwargs) if filter_kwargs else vectordb.similarity_search(query, k=3)
            except Exception as e:
                return f"Error executing similarity search: {e}"
            
            context = "\n".join([doc.page_content for doc in docs])
            if not docs and selected_notes:
                 context = "(The specifically selected file did not contain any text chunks relevant to this query.)"
            elif not docs:
                 return "I couldn't find any relevant information in your notes."
                 
            prompt = f"Use the following context to answer the question.\n\nContext:\n{context}\n\nQuestion: {query}\n\nAnswer:"
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
                return f"NVIDIA API Error: {exc}"
    return CustomQAChain()

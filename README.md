# 🧠 RecallGPT
<img width="1470" alt="Screenshot 2025-06-15 at 12 40 33 PM" src="https://github.com/user-attachments/assets/977dcfd6-9649-432b-8222-f87475d6a749" />



**RecallGPT** is a local personal assistant that lets you chat with your own markdown notes using an LLM. It also extracts tasks and expenses from your notes for easy tracking.

### 🔍 Features
- Upload `.md` notes and ask questions about them
- Chat interface powered by Ollama (e.g. LLaMA3)
- Extracts tasks and expenses using a custom parser
- Filter and view tasks and expenses with ease
- Rebuild vector DB instantly after uploading new files

### 🛠 Built With
- Streamlit (UI)
- LangChain (retrieval + chain building)
- HuggingFace Embeddings (`all-MiniLM-L6-v2`)
- ChromaDB (vector store)
- Ollama (LLM backend)

### ▶️ How to Use
1. Upload markdown notes via the sidebar
2. Click “Retrain Vector DB”
3. Ask questions in the chat interface
4. View tasks or expenses from your notes in dedicated tabs

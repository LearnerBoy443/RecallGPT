# 🧠 RecallGPT

> **Your AI-Powered Second Brain**  
> A privacy-focused personal knowledge management system that lets you chat with your notes, automatically extract tasks and expenses, remember images, and organize your life using Retrieval-Augmented Generation (RAG) and Large Language Models.

---

## 📖 Overview

RecallGPT is an AI-powered personal assistant built with **Django**, **LangChain**, and **LLMs** that transforms your markdown notes into an intelligent knowledge base.

Instead of manually searching through hundreds of notes, RecallGPT allows you to ask questions in natural language while automatically organizing actionable information like tasks, expenses, and image memories.

The application combines:

- 📝 Personal Note Management
- 💬 AI Chat (RAG)
- ✅ Automatic Task Extraction
- 💰 Intelligent Expense Tracking
- 🖼️ Image Memory with EXIF Metadata
- 📚 Multi-Session Conversations
- 🎨 AI Image Generation

---

# ✨ Features

## 📝 Markdown Note Management

- Upload Markdown (.md) and text files
- User-specific document storage
- Binary database storage
- Automatic vector indexing
- Version-friendly architecture

---

## 💬 AI Chat with Your Notes (RAG)

Ask questions such as:

> What did I spend on transportation?

> What tasks are still pending?

> What did I write about my internship?

The system performs:

```
Question
      ↓
Vector Search
      ↓
Relevant Note Chunks
      ↓
Prompt Construction
      ↓
LLM
      ↓
Answer
```

Supported LLM Backends:

- Ollama (Local)
- NVIDIA AI Endpoints
- Google Gemini (optional)

---

## 🧠 General AI Chat

Separate from note-based chat.

Features:

- Chat history
- Multiple conversations
- Independent chat sessions
- Context-aware responses

---

## ✅ Automatic Task Extraction

RecallGPT scans uploaded notes and extracts tasks automatically.

Supported formats:

```markdown
- [ ] Buy groceries
- [x] Submit assignment

TODO: Finish project

Task: Prepare presentation

Action: Call client
```

Tracks:

- Pending
- Completed

---

## 💰 Expense Tracking

Expenses are automatically detected from notes.

Examples:

```
Spent 500 on Coffee

Bought a book for 350

Petrol cost 1200

- Dinner - ₹450

- Lunch: Rs. 180
```

Supports currencies:

- ₹
- $
- €
- £
- INR
- USD
- EUR
- GBP

---

## 🖼️ Image Memory

Upload images alongside your memories.

RecallGPT stores:

- Camera model
- Capture date
- GPS location
- Description
- Tags
- Image metadata

Supports semantic image recall during conversations.

---

## 🎨 AI Image Generation

Generate AI images directly inside the application using natural language prompts.

---

## 👥 Multi User Support

Each user gets:

- Private notes
- Private vector database
- Private images
- Private chat history
- Secure authentication

---

# 🏗️ System Architecture

```
                    +--------------------+
                    |    Django Frontend |
                    +---------+----------+
                              |
                    Django REST Framework
                              |
          +-------------------+------------------+
          |                                      |
          |                                      |
      Business Logic                      Authentication
          |                                      |
          +-------------------+------------------+
                              |
                    LangChain Orchestration
                              |
         +--------------------+------------------+
         |                                       |
         |                                       |
   Embedding Model                         LLM Backend
(all-MiniLM-L6-v2)                  Ollama / NVIDIA / Gemini
         |                                       |
         +--------------------+------------------+
                              |
                      Vector Database
               ChromaDB / PostgreSQL pgvector
                              |
                    Retrieved Context
                              |
                        Final Response
```

---

# 🧩 Technology Stack

## Backend

- Django 6
- Django REST Framework

## AI

- LangChain
- Sentence Transformers
- HuggingFace Embeddings
- Ollama
- NVIDIA AI Endpoints
- Google Gemini

## Database

- PostgreSQL
- Supabase
- pgvector
- SQLite (Development)

## Vector Database

- ChromaDB
- PostgreSQL pgvector

## Image Processing

- Pillow

## Production

- Gunicorn
- WhiteNoise

---

# 📂 Project Structure

```
RecallGPT
│
├── api/
│   ├── templates/
│   ├── migrations/
│   ├── models.py
│   ├── views.py
│   ├── serializers.py
│   ├── services.py
│   ├── storage.py
│   ├── utils.py
│   ├── urls.py
│   └── admin.py
│
├── recall_project/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── notes/
│
├── manage.py
├── parsers.py
├── requirements.txt
└── README.md
```

---

# ⚙️ Workflow

## Upload Notes

```
Markdown File
      │
      ▼
Upload API
      │
      ▼
Database Storage
      │
      ▼
Chunk Documents
      │
      ▼
Generate Embeddings
      │
      ▼
Store in Vector DB
```

---

## Chat with Notes

```
Question
      │
      ▼
Similarity Search
      │
      ▼
Top Relevant Chunks
      │
      ▼
Prompt Construction
      │
      ▼
Large Language Model
      │
      ▼
Generated Answer
```

---

## Task Extraction

```
Uploaded Notes
      │
      ▼
Regex Parser
      │
      ▼
Extract Tasks
      │
      ▼
Task Dashboard
```

---

## Expense Extraction

```
Uploaded Notes
      │
      ▼
Regex Detection
      │
      ▼
Amount Parsing
      │
      ▼
Expense Dashboard
```

---

## Image Memory

```
Upload Image
      │
      ▼
Extract EXIF
      │
      ▼
Generate Metadata
      │
      ▼
Store Image
      │
      ▼
Semantic Retrieval
```

---

# 📡 API Endpoints

## HTML

| Method | Endpoint |
|---------|----------|
| GET | `/` |
| GET | `/chat/` |
| GET | `/general-chat/` |
| GET | `/tasks/` |
| GET | `/expenses/` |
| GET | `/gallery/` |
| GET | `/image-studio/` |
| GET | `/about/` |

---

## REST API

### Notes

```
POST /api/upload/

POST /api/retrain/

GET /api/notes/
```

### Chat

```
POST /api/chat/

POST /api/general_chat/

POST /api/sessions/

GET /api/sessions/

GET /api/sessions/<id>/messages/
```

### Tasks

```
GET /api/tasks/
```

### Expenses

```
GET /api/expenses/
```

### Images

```
GET /api/gallery/

POST /api/generate_image/
```

### Utilities

```
GET /api/ollama_status/

GET /api/media/serve/<filename>
```

---

# 🗄️ Database Models

## User

```
User
 ├── username
 ├── email
 └── password
```

---

## UserProfile

```
User
 └── UserProfile
      ├── phone
      └── profile picture
```

---

## ChatSession

```
ChatSession
 ├── title
 ├── type
 └── created_at
```

---

## ChatMessage

```
ChatMessage
 ├── role
 ├── content
 └── timestamp
```

---

## DatabaseFile

```
DatabaseFile
 ├── filename
 ├── binary content
 ├── size
 └── updated_at
```

---

## ImageMemory

```
ImageMemory
 ├── image
 ├── description
 ├── tags
 ├── location
 ├── camera
 └── uploaded_at
```

---

# 🔍 Supported Parsing

## Tasks

- Checkbox tasks
- TODO
- Task:
- Action:
- To-do:

---

## Expenses

Supports:

```
Spent 500

Paid 250

Bought for 300

Cost 120

Dinner - ₹450

Lunch: Rs.180
```

Multiple currencies supported.

---

# 🔒 Security

- Django Authentication
- User Isolation
- Protected REST APIs
- Separate Vector Collections
- Environment Variables
- Session Authentication

---

# 🚀 Installation

## Clone Repository

```bash
git clone https://github.com/yourusername/RecallGPT.git

cd RecallGPT
```

---

## Create Virtual Environment

```bash
python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Linux/macOS

```bash
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Environment

Create a `.env` file.

```env
SECRET_KEY=

DEBUG=True

SUPABASE_DB_HOST=

SUPABASE_DB_NAME=

SUPABASE_DB_USER=

SUPABASE_DB_PASSWORD=

SUPABASE_DB_PORT=

NVIDIA_API_KEY=
```

---

## Apply Migrations

```bash
python manage.py migrate
```

---

## Run Development Server

```bash
python manage.py runserver
```

Open:

```
http://127.0.0.1:8000
```

---

# 📈 Performance

- Cached embedding model
- Thread-safe retraining
- Batch embedding generation
- Efficient vector similarity search
- Cached aggregate notes
- User-specific vector collections

---

# 🔮 Future Enhancements

- Voice Assistant
- Mobile Application
- Browser Extension
- Real-Time Collaboration
- OCR Support
- PDF Parsing
- Calendar Integration
- Email Integration
- Better Analytics
- Fine-Tuned Models
- Multi-modal RAG
- Streaming Responses
- Docker Deployment

---

# 📜 License

This project is intended for educational and personal productivity purposes.

---

# 👨‍💻 Author

**Abhirup Chakraborty**

**RecallGPT** is a personal AI knowledge management system designed to function as a private, intelligent second brain by combining Retrieval-Augmented Generation (RAG), Large Language Models, semantic search, automated information extraction, and image memory into a single unified platform.

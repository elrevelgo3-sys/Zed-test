# 🔄 PDF to DOCX Converter

AI-powered PDF to DOCX converter with OCR support for scanned documents.

## ✨ Features

- **Smart OCR Pipeline**: Automatically detects native PDFs vs scans
- **Multiple OCR Engines**: Mistral Pixtral, DeepSeek VL2, Surya (local)
- **Visual Fidelity**: Preserves layout, tables, fonts, and formatting
- **Batch Processing**: Convert up to 5 files simultaneously
- **Multi-language**: Supports 50+ languages
- **B2B Ready**: API keys, webhooks, usage tracking

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                        │
└─────────────────────────────┬───────────────────────────────┘
                              │ REST API / WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Jobs API   │  │  Auth API   │  │ Billing API │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────┬───────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌────────────┐      ┌────────────┐      ┌────────────┐
   │ PostgreSQL │      │   Redis    │      │   MinIO    │
   │  (users)   │      │  (queue)   │      │  (files)   │
   └────────────┘      └─────┬──────┘      └────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Worker (Celery)                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              SMART OCR PIPELINE                     │    │
│  │  PDF → Analyze → OCR (if needed) → Structure → DOCX │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Redis
- PostgreSQL (optional, for production)

### Local Development

1. **Clone and setup:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Run the server:**
```bash
uvicorn app.main:app --reload --port 8000
```

4. **Run worker (separate terminal):**
```bash
celery -A app.workers.tasks worker --loglevel=info
```

### Docker

```bash
docker-compose up --build
```

## 📡 API Endpoints

### Convert PDF to DOCX

```http
POST /api/v1/convert
Content-Type: multipart/form-data

file: <PDF file>
ocr_enabled: true/false (optional)
language: "english" (optional)
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "processing",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Check Job Status

```http
GET /api/v1/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "completed",
  "progress": 100,
  "download_url": "/api/v1/download/abc123",
  "pages_processed": 15,
  "processing_time_ms": 4500
}
```

### Download Result

```http
GET /api/v1/download/{job_id}
```

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MISTRAL_API_KEY` | Mistral AI API key | required |
| `DEEPSEEK_API_KEY` | DeepSeek API key | optional |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `DATABASE_URL` | PostgreSQL URL | `sqlite:///./app.db` |
| `STORAGE_TYPE` | `local` or `s3` | `local` |
| `S3_BUCKET` | S3 bucket name | - |
| `MAX_FILE_SIZE_MB` | Max upload size | `50` |
| `MAX_PAGES` | Max pages per document | `200` |

## 🔧 OCR Pipeline

The system automatically selects the best OCR method:

1. **Native PDF** → Direct text extraction (fastest)
2. **Simple scan** → Surya local OCR (free, fast)
3. **Complex scan** → Mistral Pixtral (best quality)
4. **Tables** → DeepSeek VL2 (specialized)

## 📦 Tech Stack

- **Backend:** Python 3.11, FastAPI, Celery
- **OCR:** Mistral Pixtral, DeepSeek VL2, Surya
- **DOCX:** python-docx
- **PDF:** PyMuPDF (fitz), pdf2image
- **Queue:** Redis + Celery
- **Database:** PostgreSQL / SQLite
- **Storage:** Local / S3 / MinIO
- **Deploy:** Docker, Railway / Fly.io

## 🚢 Deployment

### Railway

```bash
railway login
railway init
railway up
```

### Fly.io

```bash
fly launch
fly deploy
```

## 📄 License

MIT License

## 🤝 Contributing

Pull requests are welcome!
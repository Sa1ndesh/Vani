# Vani-Kanoon API Documentation

Base URL: `http://localhost:8000`  
All requests and responses are JSON unless noted otherwise.

---

## Authentication

Currently, the API does not require authentication. Rate limiting is recommended for production deployments (see [Rate Limiting](#rate-limiting)).

---

## Rate Limiting

| Tier | Limit |
|------|-------|
| Development | No limit |
| Recommended Production | 60 requests/minute per IP |
| Speech endpoints | 20 requests/minute per IP |

---

## Error Codes

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Success |
| 400 | Bad Request — missing or invalid input |
| 422 | Unprocessable Entity — validation error (FastAPI) |
| 500 | Internal Server Error |
| 503 | Service Unavailable — a required backend service is not initialized |

Error response format:
```json
{
  "detail": "Description of the error"
}
```

---

## Health Check

### `GET /health`

Returns service status and which sub-services are available.

**Response:**
```json
{
  "status": "ok",
  "service": "Vani-Kanoon AI Service",
  "services": {
    "rag": true,
    "speech": false,
    "language_detector": true,
    "legal_processor": true,
    "location_service": true,
    "response_generator": true
  }
}
```

**cURL:**
```bash
curl http://localhost:8000/health
```

---

## Legal Endpoints

### `POST /legal/query`

Main voice/text query endpoint for legal assistance.

**Request Body:**
```json
{
  "query": "What is IPC Section 302?",
  "audio": "BASE64_ENCODED_AUDIO_OPTIONAL",
  "language": "English",
  "dialect": "Hubli Kannada",
  "state": "Karnataka",
  "session_id": "sess_abc123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes (if no audio) | The legal question text |
| `audio` | string (base64) | No | Base64-encoded audio (WebM/WAV/MP3) |
| `language` | string | No | Language: `English`, `Hindi`, `Kannada`, `Marathi`, `Tamil`, `Telugu` |
| `dialect` | string | No | Specific dialect (auto-detected if not provided) |
| `state` | string | No | Indian state name for state-specific laws |
| `session_id` | string | No | Session ID for conversation continuity |

**Response:**
```json
{
  "response": "IPC Section 302 prescribes punishment for murder...",
  "audio_response": "BASE64_ENCODED_MP3",
  "citations": [
    {"reference": "IPC 302", "context": "Punishment for Murder"},
    {"reference": "BNS 103", "context": "BNS equivalent"}
  ],
  "simplified_explanation": "If someone kills another person on purpose, they can be sentenced to death or life in prison.",
  "language_detected": "English",
  "dialect_detected": "Indian English",
  "query_type": "criminal",
  "session_id": "sess_abc123"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/legal/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "My landlord is demanding 6 months security deposit. Is this legal in Karnataka?",
    "language": "English",
    "state": "Karnataka"
  }'
```

---

### `POST /legal/analyze`

Analyze a legal document and extract key information.

**Request Body:**
```json
{
  "document_text": "THIS AGREEMENT is made on 1st January 2024 between...",
  "language": "English"
}
```

**Response:**
```json
{
  "summary": "This is a rental agreement between...",
  "key_sections": [],
  "risks": [],
  "recommendations": [],
  "full_analysis": "Summary: ...\n\nKey Sections: ...\n\nRisks: ...\n\nRecommendations: ..."
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/legal/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "document_text": "This rental agreement is entered into between John (Landlord) and Jane (Tenant) for premises at...",
    "language": "English"
  }'
```

---

### `POST /legal/chat`

Conversational legal assistance with session memory.

**Request Body:**
```json
{
  "message": "What are the grounds for divorce under Hindu law?",
  "language": "Hindi",
  "state": "Maharashtra",
  "session_id": "sess_xyz789"
}
```

**Response:**
```json
{
  "reply": "हिंदू विवाह अधिनियम 1955 की धारा 13 के अनुसार...",
  "session_id": "sess_xyz789"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/legal/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I file an FIR?",
    "language": "English",
    "session_id": "my_session_01"
  }'
```

---

### `GET /legal/state/{state}`

Get state-specific laws, courts, and legal information.

**Path Parameter:** `state` — e.g., `Karnataka`, `Maharashtra`, `Tamil Nadu`

**Response:**
```json
{
  "state": "Karnataka",
  "laws": {
    "tenancy": {
      "act": "Karnataka Rent Control Act 2001",
      "security_deposit": "Up to 10 months in Bengaluru; 3 months elsewhere",
      "notice_period": "3 months for eviction in Bengaluru",
      "dispute_forum": "Rent Controller (Senior Civil Judge)"
    },
    "stamp_duty": {
      "sale_deed": "5% of market value + 1% registration fee"
    },
    "key_acts": ["Karnataka Land Revenue Act 1964", "..."]
  },
  "courts": [
    {
      "name": "Karnataka High Court",
      "location": "Bengaluru",
      "jurisdiction": "Highest court for Karnataka"
    }
  ]
}
```

**cURL:**
```bash
curl http://localhost:8000/legal/state/Karnataka
```

---

## Speech Endpoints

### `POST /speech/transcribe`

Convert audio to text (Speech-to-Text).

**Request Body:**
```json
{
  "audio": "BASE64_ENCODED_AUDIO",
  "language": "Kannada"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | string (base64) | Yes | Base64-encoded audio (WebM/WAV/MP3) |
| `language` | string | No | Hint for STT model; auto-detected if omitted |

**Response:**
```json
{
  "text": "ನನ್ನ ಮನೆ ಮಾಲೀಕ ತುಂಬಾ ಬಾಡಿಗೆ ಕೇಳುತ್ತಿದ್ದಾರೆ",
  "detected_language": "Kannada"
}
```

**cURL:**
```bash
# First encode your audio file to base64
AUDIO_B64=$(base64 -w 0 my_audio.wav)

curl -X POST http://localhost:8000/speech/transcribe \
  -H "Content-Type: application/json" \
  -d "{\"audio\": \"$AUDIO_B64\", \"language\": \"Kannada\"}"
```

---

### `POST /speech/synthesize`

Convert text to speech (Text-to-Speech).

**Request Body:**
```json
{
  "text": "आपके मामले में IPC धारा 420 लागू होती है।",
  "language": "Hindi",
  "dialect": "Delhi Hindi"
}
```

**Response:**
```json
{
  "audio": "BASE64_ENCODED_MP3",
  "format": "mp3"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/speech/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your tenant rights include the right to receive a written receipt for rent paid.",
    "language": "English"
  }'
```

---

## Language Endpoint

### `GET /languages/detect`

Detect language and dialect from text.

**Query Parameter:** `text` — the text to analyze

**Response:**
```json
{
  "language": "Kannada",
  "dialect": "North Karnataka / Hubli-Dharwad",
  "region": "North Karnataka",
  "script": "Kannada",
  "confidence": 0.95
}
```

**cURL:**
```bash
curl "http://localhost:8000/languages/detect?text=ನಿಮ್ಮ%20ಮನೆ%20ಮಾಲೀಕ%20ಎಷ್ಟು%20ಡಿಪಾಸಿಟ್%20ಕೇಳ್ತಿದ್ದಾರೆ"
```

---

## Legacy Healthcare Endpoints

These endpoints are retained for backwards compatibility with the original Arogya-Vahini frontend.

### `POST /analyze`

Analyze patient symptoms and reports.

**Request Body:**
```json
{
  "symptoms": "fever, cough, headache",
  "reports": "CBC: normal"
}
```

**Response:** `{"analysis": "..."}`

---

### `POST /chat`

Legacy medical chat endpoint.

**Request Body:**
```json
{
  "session_id": "doctor_session_1",
  "message": "Patient has high fever for 3 days",
  "patient_context": "Age: 45, Blood group: B+"
}
```

**Response:** `{"reply": "..."}`

---

### `DELETE /chat/{session_id}`

Clear a legacy chat session.

**Response:** `{"status": "cleared"}`

---

## Supported Languages

| Language | ISO Code | Script | Dialects Supported |
|----------|----------|--------|-------------------|
| English | en | Latin | Indian English |
| Hindi | hi | Devanagari | Bhojpuri, Rajasthani, Delhi, Awadhi |
| Kannada | kn | Kannada | North Karnataka, Bangalore, Coastal, Mysore |
| Marathi | mr | Devanagari | Mumbai, Pune, Vidarbha, Konkan |
| Tamil | ta | Tamil | Chennai, Madurai, Coimbatore |
| Telugu | te | Telugu | Hyderabad, Coastal Andhra, Rayalaseema |

---

## Example: Full Legal Query Flow

```bash
# Step 1: Check if backend is running
curl http://localhost:8000/health

# Step 2: Ask a legal question in Hindi
curl -X POST http://localhost:8000/legal/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "मेरे मकान मालिक ने बिना नोटिस दिए बिजली काट दी। क्या यह कानूनी है?",
    "language": "Hindi",
    "state": "Delhi",
    "session_id": "user_123"
  }'

# Step 3: Follow-up in the same session
curl -X POST http://localhost:8000/legal/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "मुझे किस अदालत में शिकायत करनी चाहिए?",
    "language": "Hindi",
    "state": "Delhi",
    "session_id": "user_123"
  }'

# Step 4: Get state-specific information
curl http://localhost:8000/legal/state/Delhi
```

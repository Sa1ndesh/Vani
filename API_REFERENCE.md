# Vani-Kanoon API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

---

## Healthcare Endpoints (Arogya-Vahini)

### POST /analyze

Analyze patient symptoms and reports.

**Request**
```json
{ "symptoms": "fever, cough", "reports": "blood test normal" }
```

**Response**
```json
{ "analysis": "Possible condition: ..." }
```

---

### POST /chat

Conversational medical assistant.

**Request**
```json
{ "session_id": "abc123", "message": "What does the patient have?", "patient_context": "..." }
```

**Response**
```json
{ "reply": "Based on the symptoms..." }
```

---

### DELETE /chat/{session_id}

Clear a chat session.

---

## Legal Endpoints (Vani-Kanoon)

### POST /legal/query

Main legal query endpoint.

**Request**
```json
{
  "query": "What is the punishment for theft?",
  "language": "hi",
  "state": "Maharashtra",
  "simplified": false,
  "session_id": "user123"
}
```

**Response**
```json
{
  "answer": "Under IPC Section 379, theft is punishable with...",
  "citations": [
    {
      "section": "379",
      "title": "Punishment for theft",
      "act": "Indian Penal Code 1860",
      "description": "...",
      "score": 0.92
    }
  ],
  "language": "hi",
  "intent": "seeking_information",
  "keywords": ["theft", "punishment"],
  "entities": { "sections": ["379"] },
  "session_id": "user123"
}
```

---

### POST /legal/analyze

Analyze a legal document or text passage.

**Request**
```json
{
  "text": "The landlord served a 30-day eviction notice...",
  "language": "en"
}
```

**Response**
```json
{
  "analysis": "This appears to be a tenancy dispute...",
  "entities": { "sections": [], "acts": ["Rent Control Act"] },
  "keywords": ["eviction", "notice", "landlord"],
  "language": "en"
}
```

---

### POST /legal/chat

Conversational legal assistance (maintains session context).

**Request**
```json
{
  "session_id": "legal_session_1",
  "message": "Can my landlord evict me without notice?",
  "language": "kn",
  "state": "Karnataka"
}
```

**Response**
```json
{
  "reply": "ಇಲ್ಲ, ಮಾಲೀಕರು ನೋಟಿಸ್ ಇಲ್ಲದೆ...",
  "session_id": "legal_session_1",
  "language": "kn"
}
```

---

### GET /legal/state/{state}

Get state-specific laws and court information.

**Example:** `GET /legal/state/Maharashtra`

**Response**
```json
{
  "state": "Maharashtra",
  "laws": {
    "act_name": "Maharashtra Rent Control Act 1999",
    "key_provisions": [...],
    "notice_periods": { "eviction": "30 days", "rent_revision": "90 days" }
  },
  "courts": {
    "high_court": "Bombay High Court",
    "district_courts": [...],
    "legal_aid": { "phone": "1516", "website": "https://slsa.maharashtra.gov.in" }
  }
}
```

---

### POST /legal/simplified-explain

Get a plain-language, child-friendly explanation.

**Request**
```json
{
  "query": "What is Section 302 IPC?",
  "section": "302",
  "act": "IPC",
  "language": "hi"
}
```

**Response**
```json
{
  "explanation": "धारा 302 का मतलब है जब कोई जानबूझकर किसी की जान ले लेता है...",
  "section": "302",
  "act": "IPC",
  "language": "hi"
}
```

---

### GET /legal/search

Search the legal database.

**Query Parameters**
- `q` (required): Search term
- `state` (optional): Filter by state
- `top_k` (optional, default 10): Number of results (1–50)

**Example:** `GET /legal/search?q=domestic+violence&state=Delhi&top_k=5`

**Response**
```json
{
  "results": [
    {
      "section": "3",
      "title": "Definition of domestic violence",
      "act": "Protection of Women from Domestic Violence Act 2005",
      "score": 0.88
    }
  ],
  "query": "domestic violence",
  "count": 5
}
```

---

## Speech Endpoints

### POST /speech/transcribe

Convert audio to text (Speech-to-Text).

**Request**
```json
{
  "audio": "<base64-encoded audio bytes>",
  "language": "hi"
}
```

**Response**
```json
{
  "text": "मेरे मकान मालिक ने मुझे निकाल दिया",
  "language": "hi",
  "confidence": 0.95
}
```

---

### POST /speech/synthesize

Convert text to speech (Text-to-Speech).

**Request**
```json
{
  "text": "आपका अधिकार है कि...",
  "language": "hi",
  "slow": false
}
```

**Response**
```json
{
  "audio": "<base64-encoded MP3 bytes>",
  "language": "hi",
  "format": "mp3"
}
```

---

## Language Detection

### POST /languages/detect

Detect language and dialect from text.

**Request**
```json
{ "text": "ನನ್ನ ಮನೆ ಬಾಡಿಗೆ ಬಗ್ಗೆ ಪ್ರಶ್ನೆ ಇದೆ" }
```

**Response**
```json
{
  "language": "kn",
  "confidence": 0.97,
  "script": "Kannada",
  "dialect": {
    "dialect": "bangalore",
    "confidence": 0.72,
    "display_name": "Bangalore Kannada"
  }
}
```

---

## Supported Languages

| Code | Language | Script |
|------|----------|--------|
| `hi` | Hindi | Devanagari |
| `kn` | Kannada | Kannada |
| `mr` | Marathi | Devanagari |
| `ta` | Tamil | Tamil |
| `te` | Telugu | Telugu |
| `en` | English | Latin |

---

## Error Responses

All endpoints return standard HTTP error codes:

| Code | Meaning |
|------|---------|
| 400 | Bad request (missing required fields) |
| 500 | Internal server error (check logs) |

Error body:
```json
{ "detail": "Error description here" }
```

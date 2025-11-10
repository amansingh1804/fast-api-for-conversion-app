# Word to XML Conversion API

This FastAPI application wraps your Python ML-based conversion algorithm.

## Local Testing

1. **Install Dependencies:**
```bash
cd api
pip install -r requirements.txt
```

2. **Run the Server:**
```bash
uvicorn app:app --reload
```

The API will run at `http://localhost:8000`

3. **Test Health Check:**
```bash
curl http://localhost:8000/health
```

4. **View Interactive API Documentation:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Deployment Options

### Option 1: Railway (Easiest)
1. Create account at https://railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Connect your repository
4. Railway auto-detects Python and uses `requirements.txt`
5. Set root directory to `/api`
6. Copy the deployed URL

### Option 2: Render
1. Create account at https://render.com
2. Click "New" → "Web Service"
3. Connect your repository
4. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Root Directory:** `api`
5. Deploy and copy the URL

### Option 3: Google Cloud Run
1. Install Google Cloud SDK
2. Build and deploy:
```bash
gcloud run deploy word-to-xml-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Option 4: AWS Lambda (Advanced)
Use Mangum to deploy FastAPI to Lambda with API Gateway.

## API Endpoints

### Health Check
```
GET /health
```
Response:
```json
{
  "status": "healthy",
  "message": "API is running"
}
```

### Convert Document
```
POST /convert
```
Form Data:
- `dtd_file`: DTD XML file (optional, for context)
- `word_file`: Word document (.doc or .docx)

Response (Success):
```json
{
  "success": true,
  "xml_content": "<?xml version=\"1.0\"...",
  "word_filename": "document.docx"
}
```

Response (Error):
```json
{
  "success": false,
  "error": "Error message",
  "error_type": "ValueError"
}
```

## Environment Variables

None required for basic usage. For production:
- `FLASK_ENV=production`
- `MAX_CONTENT_LENGTH=52428800` (50MB limit)

## Next Steps

After deploying:
1. Copy your API URL (e.g., `https://your-app.railway.app`)
2. Update the React app's API endpoint in `/components/ConversionWorkflow.tsx`
3. Replace `YOUR_API_URL_HERE` with your actual URL

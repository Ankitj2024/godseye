# God's Eye

> Upload one drone video. Get back a usable 3D world model.

**God's Eye** is an AI-assisted 3D scene reconstruction tool for drone footage. Upload a single drone video, and receive a navigable 3D scene with object-level understanding, confidence signals, and exportable assets.

## Architecture

- **Frontend**: React + TypeScript (Vite)
- **Backend**: Python + FastAPI
- **Storage**: Local filesystem
- **Compute**: Modal GPU workers (hackathon), on-prem GPU (production)
- **Reconstruction**: COLMAP + Open3D
- **AI**: Depth estimation, semantic detection, generative completion

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## Project Structure

```
godseye/
├── frontend/          # React + TypeScript app
├── backend/           # FastAPI backend
├── shared/            # Shared schemas and config
├── data/              # Local file storage (gitignored)
├── docs/              # Documentation
├── architecture.md    # System architecture
├── development_plan.md # Build plan
├── prd.md             # Product requirements
└── requirements.txt   # Python dependencies
```

## Modes

- **Exact Reconstruction**: Faithful geometry from observed evidence only
- **Generative Reconstruction**: AI-completed scene with asset library insertion

## License

Hackathon project — license TBD.

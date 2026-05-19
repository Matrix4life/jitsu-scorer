# Jiu-Jitsu Pose Scorer

AI-powered BJJ position detection and automatic scoring using TensorFlow pose estimation + OpenAI vision classification.

## Features

- **Real-time pose detection** — TensorFlow.js MoveNet tracks both fighters simultaneously
- **Multi-person grapple identification** — Automatically assigns Fighter A (blue) and Fighter B (orange)
- **AI position classification** — OpenAI GPT-4o-mini analyzes the position using biomechanics rules
- **Temporal smoothing** — Confirms positions across 3 frames to eliminate flickering misclassifications
- **Automatic scoring** — Award points for mount (4), side control (3), back control (4), knee on belly (2)
- **Manual override** — Tap "Submission" or swap fighters at any time
- **Live skeleton overlay** — See detected joints and bones in real-time

## Deployment (Railway)

### 1. Create a GitHub repo

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/jitsu-scorer.git
git push -u origin main
```

### 2. Deploy to Railway

1. Go to https://railway.app
2. Sign up with GitHub (free tier)
3. Create new project → "Deploy from GitHub"
4. Select your `jitsu-scorer` repo
5. Railway auto-detects Python and deploys

### 3. Add your OpenAI API key

1. In Railway dashboard, go to your project
2. Click "Variables" (or Secrets)
3. Add environment variable:
   - **Key:** `OPENAI_API_KEY`
   - **Value:** Your key from https://platform.openai.com/api-keys
4. Click Deploy to apply

### 4. Get your live URL

In Railway, you'll see a URL like:
```
https://jitsu-scorer-production.up.railway.app
```

Open it on your phone → grant camera permission → tap "Toggle Camera" → start rolling!

## Files

- **server-improved.py** — Python backend (Flask-like HTTP server)
  - Serves `index.html`
  - Receives video frames + keypoints via POST `/api/classify`
  - Calls OpenAI GPT-4o-mini with image + keypoint data
  - Returns position classification with confidence

- **index.html** — Frontend React/Vanilla JS
  - Loads TensorFlow.js + MoveNet
  - Detects 2 fighters, assigns persistent A/B IDs
  - Draws skeleton overlays (blue/orange)
  - Every 3 seconds, sends frame + keypoints to server for AI classification
  - Maintains temporal smoothing buffer for confident position changes
  - Auto-scores when position changes confirmed

- **requirements.txt** — Python dependencies (empty, using standard library)

## How It Works

### Pose Detection Flow

1. **Browser** loads video from phone camera
2. **MoveNet** detects up to 13 keypoints per person (poses)
3. **Grapple detection** — finds the two closest poses (ignores referee)
4. **Keypoint extraction** — normalizes joint positions to 0-1 scale
5. **Server sends** — image (canvas frame) + keypoint data to OpenAI
6. **GPT-4o-mini analyzes:**
   - "Fighter A's hips are at (0.45, 0.62), Fighter B's shoulders at (0.50, 0.45)"
   - "Since A's hips are above B's shoulders → MOUNT position"
   - Returns `{position: "mount", top_fighter: "A", confidence: "high"}`
7. **Temporal smoothing** — buffer confirms mount 2/3 times → score 4 points
8. **Display updates** — skeleton overlays, score cards, move log

### Biomechanics Rules

The system uses precise detection rules:

- **Mount:** Top fighter's hips above bottom's shoulders, both legs straddled
- **Guard:** Bottom fighter's knees raised, legs wrapped or in front of top
- **Side control:** Top fighter perpendicular (shoulders wide apart), hips at bottom's chest level
- **Knee on belly:** One knee between shoulder and hip, other leg posted
- **Back control:** Bodies close and parallel, top fighter behind
- **Standing:** Both fighters upright, far apart

## Costs

- **Railway:** Free tier includes $5/month credits (plenty for testing)
- **OpenAI:** ~$0.01-0.05 per API call (3 calls per frame, ~1 frame per 3 seconds)
  - Example: 1 hour of scoring ≈ 1200 calls ≈ $12-60 (depending on volume)
  - Free trial includes $5 in credits

## Improving Detection

### Option 1: Better Prompting (FREE)
The `server-improved.py` already includes detailed biomechanics rules. Tweak the prompt to match your camera angle/lighting.

### Option 2: User Corrections (FREE)
Add a "Correct Position" button. Store corrections locally. After 50+ corrections, you have training data.

### Option 3: Fine-tune GPT (Paid, ~$5-20)
Use Replicate.com to fine-tune a vision model on your labeled dataset. Get a custom model that understands your specific setup.

## Troubleshooting

**"OPENAI_API_KEY not set"**
- Go to Railway → Variables → add `OPENAI_API_KEY`

**"Camera permission denied"**
- Click "Allow" when browser asks for camera access
- Check phone Settings → Apps → Camera permissions

**"AI keeps misclassifying"**
- Improve lighting (move to brighter area)
- Ensure both fighters are visible in frame
- Wait for smoothing buffer to confirm (watch status bar)
- Try adjusting the prompt in `server-improved.py`

**"Server not responding"**
- Check Railway dashboard — deployment may be in progress
- Refresh the page
- Ensure `OPENAI_API_KEY` is set in Railway Variables

## Next Steps

1. Deploy to Railway (15 mins)
2. Test with your training partners
3. Collect corrections for 1-2 weeks
4. Fine-tune a custom model for 99% accuracy (optional)
5. Share live URL with your gym/team

## License

MIT — use freely, modify as needed.

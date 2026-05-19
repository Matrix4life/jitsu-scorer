import os
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'

# Enhanced prompt with biomechanics-based detection rules
BJJ_PROMPT = """You are an expert BJJ referee analyzing a live match frame by frame.

Two fighters are visible: Fighter A (BLUE skeleton) and Fighter B (ORANGE skeleton).
Your job: identify the current position and who has top control.

KEYPOINT COORDINATES:
- (0,0) = top-left of frame; (1,1) = bottom-right
- x: 0 = left edge, 1 = right edge
- y: 0 = top of frame, 1 = bottom of frame
- Higher y value = lower in frame

POSITION DETECTION RULES (apply biomechanics logic):

**MOUNT (4 pts):**
- Top fighter's hips are AT or ABOVE bottom fighter's chest/shoulders
- Top fighter's knees are OUTSIDE bottom fighter's hips (straddling)
- Verify: top_hips_y <= bottom_shoulders_y + 0.08
- Verify: abs(top_left_shoulder.x - top_right_shoulder.x) SMALL (top is centered, not sideways)
- Verify: Both bodies roughly vertical (not horizontal)

**GUARD (0 pts, defensive):**
- Bottom fighter's KNEES are RAISED (knees_y < hips_y by at least 0.06)
- Bottom fighter's legs are IN FRONT OF or around top fighter
- Bodies overlapping in horizontal plane (distance between centers < 0.4)
- Verify: bottom_left_knee.y < bottom_left_hip.y - 0.06 AND bottom_right_knee.y < bottom_right_hip.y - 0.06
- Look for a triangular leg position or leg wrap around top fighter

**SIDE CONTROL (3 pts):**
- Top fighter is lying PERPENDICULAR across bottom fighter's torso
- Top fighter's shoulders are WIDE APART (horizontal span > 0.22)
- Top fighter's hips are at bottom fighter's chest/shoulder level
- Verify: abs(top_left_shoulder.x - top_right_shoulder.x) > 0.22
- Verify: bottom_shoulders_y - 0.05 < top_hips_y < bottom_hips_y + 0.10
- Verify: bodies NOT stacked directly on top of each other (not mount)

**KNEE ON BELLY (2 pts):**
- Top fighter has ONE KNEE pressing into bottom fighter's abdomen/ribs
- That knee sits between bottom's shoulder and hip levels
- Other leg is POSTED OUT for balance (stretched out to the side/front)
- Verify: bottom_shoulders_y < top_knee_y < bottom_hips_y + 0.05
- Verify: Asymmetry in top fighter's leg positions (one knee bent/raised, other extended)
- Bottom fighter is typically on their back (supine)

**BACK CONTROL (4 pts):**
- Top fighter is BEHIND bottom fighter (higher x variation if side-by-side, or top's nose beyond bottom's)
- Bodies are VERY CLOSE and roughly same height in frame
- Top fighter has hooks or body lock (wrapping)
- Verify: distance between centers < 0.28
- Verify: abs(top_hips_y - bottom_hips_y) < 0.12 (similar vertical level)
- Verify: bodies in line or slightly rotated (not perpendicular like side control)

**HALF GUARD:**
- Bottom fighter has ONE leg wrapped around top fighter's leg/hip
- Other leg is free or slightly bent
- Top fighter is above but partially controlled
- Less vertical separation than full guard

**TURTLE:**
- Bottom fighter is on all fours (face down, butt up, on knees/hands)
- Top fighter is behind or attacking from above/side
- Verify: bottom_shoulders_y WELL ABOVE bottom_hips_y (back is rounded)
- Verify: bottom's knees and hands visible, ready to roll

**STANDING:**
- Both fighters are UPRIGHT on their feet
- Hips and shoulders are at similar heights (no one above the other)
- Large vertical separation (distance > 0.5)
- Verify: Both top_hips_y and bottom_hips_y are in upper portion of frame (y < 0.5)

**UNKNOWN:**
- Positions don't clearly match above rules
- Low confidence in classification

DECISION LOGIC:
1. Look at the KEYPOINT DATA first — it is objective, reliable, never wrong
2. Use the image to verify and add context (are they moving? tense? relaxed?)
3. Determine TOP FIGHTER: who is physically higher/controlling? (lower y-value = higher in frame = usually on top)
4. Return confidence: "high" if keypoints clearly match rules, "medium" if mostly matches, "low" if uncertain

Output ONLY a JSON object, no text before or after:
{"position": "mount"|"guard"|"side_control"|"knee_on_belly"|"back_control"|"half_guard"|"turtle"|"standing"|"unknown", "top_fighter": "A"|"B"|null, "confidence": "high"|"medium"|"low"}

Examples:
- If Fighter A's hips are above Fighter B's shoulders and knees straddled → {"position": "mount", "top_fighter": "A", "confidence": "high"}
- If Fighter B's knees are raised with legs wrapped → {"position": "guard", "top_fighter": "A", "confidence": "high"}
- If Fighter A is perpendicular with wide shoulders and hips at B's chest → {"position": "side_control", "top_fighter": "A", "confidence": "high"}
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress per-request noise

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self._serve_file('index.html', 'text/html')
        elif self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/classify':
            self._classify()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _classify(self):
        if not OPENAI_API_KEY:
            self._send_json({'error': 'OPENAI_API_KEY not set — add it in Secrets'}, 500)
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            image_data = body.get('image', '')
            keypoints  = body.get('keypoints', {})

            # Ensure image is a data URL
            if not image_data.startswith('data:'):
                image_data = 'data:image/jpeg;base64,' + image_data

            # Format keypoint data into a readable string
            kp_lines = []
            for fighter, kps in keypoints.items():
                if not kps:
                    kp_lines.append(f"Fighter {fighter}: (no keypoints detected)")
                    continue
                parts = ', '.join(
                    f"{joint}({v['x']},{v['y']})" for joint, v in sorted(kps.items())
                )
                kp_lines.append(f"Fighter {fighter}: {parts}")

            kp_context = '\n\nKEYPOINT DATA (use this for accurate detection):\n' + '\n'.join(kp_lines)
            full_prompt = BJJ_PROMPT + kp_context

            payload = json.dumps({
                'model': 'gpt-4o-mini',
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text',      'text': full_prompt},
                        {'type': 'image_url', 'image_url': {'url': image_data, 'detail': 'low'}}
                    ]
                }],
                'max_tokens': 100,
                'temperature': 0.1  # Low temp = deterministic, follow rules strictly
            }).encode()

            req = urllib.request.Request(
                OPENAI_URL,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {OPENAI_API_KEY}'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=12) as resp:
                result = json.loads(resp.read())

            raw_text = result['choices'][0]['message']['content'].strip()

            # Extract JSON from response
            start = raw_text.find('{')
            end   = raw_text.rfind('}') + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(raw_text[start:end])
                except json.JSONDecodeError:
                    parsed = {'position': 'unknown', 'top_fighter': None, 'confidence': 'low'}
            else:
                parsed = {'position': 'unknown', 'top_fighter': None, 'confidence': 'low'}

            self._send_json(parsed)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            print(f'OpenAI HTTP {e.code}: {err_body[:300]}')
            try:
                err_json = json.loads(err_body)
                reason = err_json.get('error', {}).get('message', err_body[:120])
            except Exception:
                reason = err_body[:120]
            self._send_json({'position': 'unknown', 'top_fighter': None,
                             'confidence': 'low', 'error': f'HTTP {e.code}: {reason}'})
        except Exception as e:
            print(f'classify error: {e}')
            self._send_json({'position': 'unknown', 'top_fighter': None,
                             'confidence': 'low', 'error': str(e)})

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'BJJ Scorer server running on port {port}')
    print(f'Using OpenAI gpt-4o-mini with biomechanics-based position detection')
    server.serve_forever()

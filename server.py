import os
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import mimetypes

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'

BJJ_PROMPT = """You are a BJJ position identifier. Your ONLY job: Identify which of 9 positions you see.

DO NOT try to detect sweeps, escapes, passes, or submissions. ONLY positions.

Two fighters: A (BLUE skeleton) and B (ORANGE skeleton).

COORDINATE SYSTEM:
- x: 0=left edge, 1=right edge
- y: 0=top of frame (higher up), 1=bottom of frame (lower down)
- LOWER y value = HIGHER in frame = ON TOP = dominant position

ALGORITHM (follow strictly):

STEP 1: Calculate each fighter's body center
- Fighter A center_y = average(A_shoulders_y, A_hips_y)
- Fighter B center_y = average(B_shoulders_y, B_hips_y)
- Who has lower center_y? → They are on top

STEP 2: Measure key distances
- Shoulder width = abs(left_shoulder.x - right_shoulder.x)
- Knee height = are knees ABOVE hips? (knees_y < hips_y?)
- Body distance = distance between centers
- Hips height difference = abs(A_hips_y - B_hips_y)

STEP 3: Match to ONE position using these rules ONLY:

---

**POSITION 1: MOUNT**
- TOP fighter's hips are ABOVE bottom fighter's shoulders
  → Check: top_hips_y < bottom_shoulders_y - 0.09
- TOP fighter's knees are SPREAD WIDE (straddling)
  → Check: top_left_knee.x and top_right_knee.x are far apart
- Bodies form T-shape with top on bottom
- Bottom fighter is on back, arms extended
→ CONFIDENCE: HIGH only if hips clearly above shoulders AND knees spread
→ CONFIDENCE: LOW if uncertain

---

**POSITION 2: SIDE CONTROL**
- TOP fighter is PERPENDICULAR (90 degrees) across bottom's torso
- TOP fighter's SHOULDERS are WIDE (> 0.23 apart horizontally)
  → Check: abs(top_left_shoulder.x - top_right_shoulder.x) > 0.23
- TOP fighter's hips are at BOTTOM fighter's CHEST/SHOULDER level
  → Check: bottom_shoulders_y - 0.05 < top_hips_y < bottom_hips_y
- Bodies are NOT stacked vertically (perpendicular, not mount)
→ CONFIDENCE: HIGH if shoulder width > 0.23 AND hips at correct height
→ CONFIDENCE: LOW otherwise

---

**POSITION 3: BACK CONTROL**
- TOP fighter is BEHIND bottom fighter (both parallel)
- Bodies are VERY CLOSE (distance < 0.26)
  → Check: distance between centers < 0.26
- HIPS are at SAME HEIGHT (within 0.09)
  → Check: abs(top_hips_y - bottom_hips_y) < 0.09
- Bodies are parallel (same orientation), not perpendicular
→ CONFIDENCE: HIGH if both distance < 0.26 AND hips aligned
→ CONFIDENCE: LOW if uncertain

---

**POSITION 4: NORTH-SOUTH**
- Both fighters UPRIGHT (standing or high posture)
- Bodies PERPENDICULAR (90 degrees to each other)
- Top fighter's head toward bottom's legs/feet area
- Bodies VERY CLOSE (distance < 0.36)
  → Check: distance between centers < 0.36
- Both have shoulders above hips (both upright)
→ CONFIDENCE: HIGH if perpendicular AND close AND both upright
→ CONFIDENCE: LOW if uncertain

---

**POSITION 5: CLOSED GUARD**
- BOTTOM fighter has BOTH KNEES RAISED (legs pulled up)
  → Check: bottom_left_knee.y < bottom_hips_y - 0.10 AND bottom_right_knee.y < bottom_hips_y - 0.10
- Knees are CLOSE TOGETHER (not spread wide)
  → Check: abs(bottom_left_knee.x - bottom_right_knee.x) < 0.15
- Bodies OVERLAP (distance < 0.36)
  → Check: distance between centers < 0.36
- Top fighter is BETWEEN bottom's knees
→ CONFIDENCE: HIGH if BOTH knees up AND close together AND overlapping
→ CONFIDENCE: LOW if uncertain

---

**POSITION 6: OPEN GUARD**
- BOTTOM fighter has BOTH KNEES RAISED (legs up)
  → Check: bottom_left_knee.y < bottom_hips_y - 0.09 AND bottom_right_knee.y < bottom_hips_y - 0.09
- Knees are SPREAD WIDE APART (not close)
  → Check: abs(bottom_left_knee.x - bottom_right_knee.x) > 0.18
- Bodies OVERLAP but less contact than Closed Guard
  → Check: distance between centers < 0.40
- Legs are in FRONT of top (not wrapped around)
→ CONFIDENCE: HIGH if BOTH knees up AND wide apart AND overlapping
→ CONFIDENCE: LOW if uncertain

---

**POSITION 7: HALF GUARD**
- BOTTOM fighter has ASYMMETRIC leg position
  → One knee is UP (raised above hip)
  → Other leg is EXTENDED or LESS raised
  → Check: one_knee.y < hips_y AND other_knee.y >= hips_y OR one_leg_extended
- Bodies OVERLAP (distance < 0.38)
  → Check: distance between centers < 0.38
- NOT symmetrical like Closed Guard
- One of bottom's legs wrapping around one of top's legs
→ CONFIDENCE: HIGH if clear asymmetry in leg positions
→ CONFIDENCE: LOW if both legs equally raised (that's Closed Guard)

---

**POSITION 8: BUTTERFLY GUARD**
- BOTTOM fighter on back with BOTH FEET on GROUND (not extended)
- BOTH KNEES RAISED and CLOSE TOGETHER (butterfly shape)
  → Check: bottom_left_knee.y < bottom_hips_y - 0.08 AND bottom_right_knee.y < bottom_hips_y - 0.08
  → Check: abs(bottom_left_knee.x - bottom_right_knee.x) < 0.14 (knees close)
- Feet/ankles are TOGETHER or TOUCHING (soles facing up)
  → Check: bottom_left_ankle close to bottom_right_ankle
- Feet pressing into top fighter's hips/torso
- Bodies OVERLAP (distance < 0.36)
→ CONFIDENCE: HIGH if knees raised AND together AND feet together
→ CONFIDENCE: LOW if uncertain

---

**POSITION 9: TURTLE**
- BOTTOM fighter on ALL FOURS (hands and knees visible)
  → Shoulders, hips, knees all visible and engaged
- BACK is ROUNDED (shoulders/head well above hips)
  → Check: shoulders_y << hips_y (much higher)
- BUTT UP, HEAD DOWN (defensive crouch)
- TOP fighter attacking from behind or side
→ CONFIDENCE: HIGH if all-fours posture is clear AND back rounded
→ CONFIDENCE: LOW if uncertain

---

**IF NONE OF THE 9 MATCH:**
- Return: {"position": "unknown", "top_fighter": null, "confidence": "low"}

---

CRITICAL RULES:
1. If ANY keypoints are MISSING or have low confidence (< 0.2) → return "unknown"
2. If you're HESITATING between 2 positions → return "unknown" (don't guess)
3. NEVER force a match. If unsure, say "unknown" with "low" confidence
4. Use keypoint measurements as ABSOLUTE TRUTH
5. Image is secondary context only

OUTPUT: Return ONLY valid JSON, no other text:
{"position": "mount"|"side_control"|"back_control"|"north_south"|"closed_guard"|"open_guard"|"half_guard"|"butterfly_guard"|"turtle"|"unknown", "top_fighter": "A"|"B"|null, "confidence": "high"|"low"}

EXAMPLE OUTPUTS:
- {"position": "mount", "top_fighter": "A", "confidence": "high"}
- {"position": "closed_guard", "top_fighter": "B", "confidence": "high"}
- {"position": "unknown", "top_fighter": null, "confidence": "low"}
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self._serve_file('public/index.html', 'text/html')
        elif self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        else:
            # Try to serve static files from public folder
            file_path = self.path.lstrip('/')
            if os.path.exists(f'public/{file_path}'):
                mime_type, _ = mimetypes.guess_type(f'public/{file_path}')
                self._serve_file(f'public/{file_path}', mime_type or 'application/octet-stream')
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
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'File not found')

    def _classify(self):
        if not OPENAI_API_KEY:
            self._send_json({'error': 'OPENAI_API_KEY not set — add it in Railway Variables'}, 500)
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            image_data = body.get('image', '')
            keypoints  = body.get('keypoints', {})

            if not image_data.startswith('data:'):
                image_data = 'data:image/jpeg;base64,' + image_data

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
                'temperature': 0.1
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
    server.serve_forever()

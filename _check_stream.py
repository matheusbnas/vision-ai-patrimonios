import requests
r = requests.get(
    'http://10.50.3.11:5002/stream?CODE=001175&KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHJlYW0tY2xpZW50IiwianRpIjoiMzY0MTE3MzEtMmYzNy00ZDY5LThhNjctMzM1YTc5MGIwMGExIiwiaWF0IjoxNzg0NzQ2NTYwLCJleHAiOjE3ODQ3NTAxNjB9.q9urm7XADOGX3OvBY4jFqBQgaMHwK5BaNpQaXQkYQfA',
    timeout=5
)
html = r.text

import re
# Find all src attributes
sources = re.findall(r'src=[\'"]([^\'"]+)[\'"]', html)
print("=== SRC attributes ===")
for s in sources[:20]:
    print(f"  {s}")

# Check for video-related keywords
for kw in ['video', '.mp4', '.mjpeg', '.m3u8', '.ts', 'canvas', 'websocket', 'stream', 'hls']:
    count = html.lower().count(kw)
    if count > 0:
        print(f"\n'{kw}': {count} occurrences")

print(f"\nContent-Type: {r.headers.get('content-type', 'unknown')}")
print(f"HTML size: {len(html)} bytes")

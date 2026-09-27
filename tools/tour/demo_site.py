"""The site the product tour audits: a small business with real SEO problems.

Nothing here is a mock of Signal - it is a mock of a *customer's* site, so every
screenshot in the tour shows Signal's real output about real (if invented) HTML.
The flaws are deliberate and chosen to make each check in the audit say something
interesting: a short title, no meta description, an image with no alt text, no
canonical, no structured data.

It also answers WordPress's REST API, so the tour can show a connected CMS and an
applied fix changing the live page.

    python tools/tour/demo_site.py        # http://fernandfox.localhost:8901
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 8901
ORIGIN = "http://fernandfox.localhost:8901"

STATE = {"title": "Coffee", "description": "", "alt": {"/beans.jpg": "", "/roastery.jpg": ""}}


def page_html() -> str:
    desc = f'\n  <meta name="description" content="{STATE["description"]}">' if STATE["description"] else ""
    images = "".join(
        f'\n    <img src="{src}"' + (f' alt="{alt}"' if alt else "") + ' width="640" height="420">'
        for src, alt in STATE["alt"].items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{STATE['title']}</title>{desc}
</head>
<body>
  <h1>Fern &amp; Fox Coffee Roasters</h1>
  <p>We roast in small batches in Bristol and ship within a day of roasting. Every bag carries the
     farm, the altitude and the roast date, because those are the three things that actually tell you
     how a coffee will taste.</p>
  <h3>Our current roasts</h3>
  <p>Six single origins and two blends, rotating with the harvest. The espresso blend has been the
     same for nine years and we have no plans to change it.</p>{images}
  <p>Wholesale enquiries welcome. We supply eleven cafes across the south west.</p>
</body>
</html>"""


POST = {"id": 12, "link": f"{ORIGIN}/", "type": "page"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, content_type="application/json", code=200):
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _meta(self):
        return {"_yoast_wpseo_title": STATE["title"], "_yoast_wpseo_metadesc": STATE["description"]}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(page_html(), "text/html")
        if path == "/wp-json/wp/v2/users/me":
            return self._send({"name": "Fern & Fox", "id": 1})
        if path in ("/wp-json/wp/v2/pages", "/wp-json/wp/v2/posts"):
            items = [{**POST, "meta": self._meta()}] if path.endswith("pages") else []
            return self._send(items)
        if path == "/wp-json/wp/v2/media":
            return self._send([
                {"id": 31, "source_url": f"{ORIGIN}/beans.jpg", "alt_text": STATE["alt"]["/beans.jpg"]},
                {"id": 32, "source_url": f"{ORIGIN}/roastery.jpg", "alt_text": STATE["alt"]["/roastery.jpg"]},
            ])
        return self._send({"message": "Not Found"}, code=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        path = self.path.split("?")[0]
        if re.match(r"^/wp-json/wp/v2/(pages|posts)/12$", path):
            for key, value in (body.get("meta") or {}).items():
                if key == "_yoast_wpseo_title":
                    STATE["title"] = value
                elif key == "_yoast_wpseo_metadesc":
                    STATE["description"] = value
            return self._send({**POST, "meta": self._meta()})
        match = re.match(r"^/wp-json/wp/v2/media/(\d+)$", path)
        if match:
            src = "/beans.jpg" if match.group(1) == "31" else "/roastery.jpg"
            STATE["alt"][src] = body.get("alt_text", "")
            return self._send({"id": int(match.group(1)), "alt_text": STATE["alt"][src]})
        return self._send({"message": "Not Found"}, code=404)


if __name__ == "__main__":
    print(f"demo site on {ORIGIN}")
    HTTPServer((HOST, PORT), Handler).serve_forever()

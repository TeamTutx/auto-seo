import httpx

USER_AGENT = "SignalSEOBot/0.1 (+https://signal.app/bot)"


def fetch_html(url: str, timeout: float = 15.0) -> str:
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text

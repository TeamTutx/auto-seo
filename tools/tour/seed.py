"""Build the database the product tour is screenshotted against.

Everything here is invented. It writes to its own SQLite file, never the dev
database and obviously never production, so the tour can show a fully populated
account without any real customer's data appearing in a public page.

Rank positions, keyword ideas and visibility readings are inserted directly
rather than fetched: every one of those is a paid SerpApi or OpenAI call in real
life, and a screenshot is not worth spending the owner's money on. The *audits*
are real - they run against tools/tour/demo_site.py, so the checks, the score and
the messages in the screenshots are genuine output, not a mock-up.

    DATABASE_URL=sqlite:///tour.db python tools/tour/seed.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import (
    KeywordIdea, KeywordRank, Page, Product, Site, User, VisibilityAdvice, VisibilityCheck,
)
from app.security import hash_password

ORIGIN = "http://fernandfox.localhost:8901"
EMAIL = "tour@fernandfox.example"
PASSWORD = "tour-demo-account"
NOW = datetime.utcnow()


def main() -> None:
    create_db_and_tables()
    with Session(engine) as s:
        if s.exec(select(User).where(User.email == EMAIL)).first():
            print("already seeded"); return

        user = User(email=EMAIL, hashed_password=hash_password(PASSWORD), credits_balance=48)
        s.add(user); s.commit(); s.refresh(user)

        site = Site(user_id=user.id, domain="fernandfox.localhost:8901", verified=True,
                    verification_method="file_upload", verification_token="tour-token")
        # The domain column is only a label here; the pages carry the real URL.
        s.add(site); s.commit(); s.refresh(site)

        page = Page(site_id=site.id, url=f"{ORIGIN}/", target_keyword="speciality coffee bristol",
                    discovered_via="sitemap", index_status="indexed", index_source="gsc",
                    index_detail="Submitted and indexed", index_checked_at=NOW - timedelta(hours=6))
        s.add(page); s.commit(); s.refresh(page)

        # Rank history: a keyword that moved, so the chart has a shape.
        for days, pos in [(28, None), (21, 47), (14, 31), (7, 22), (0, 14)]:
            s.add(KeywordRank(page_id=page.id, keyword="speciality coffee bristol", rank_position=pos,
                              provider="serpapi", checked_at=NOW - timedelta(days=days)))
        for days, pos in [(14, 8), (7, 6), (0, 5)]:
            s.add(KeywordRank(page_id=page.id, keyword="coffee subscription bristol", rank_position=pos,
                              provider="serpapi", checked_at=NOW - timedelta(days=days)))

        s.add_all([
            KeywordIdea(site_id=site.id, keyword="speciality coffee bristol", source="gsc", targeted=True,
                        impressions=1840, clicks=61, position=14.2),
            KeywordIdea(site_id=site.id, keyword="coffee subscription bristol", source="gsc", targeted=True,
                        impressions=920, clicks=48, position=5.4),
            KeywordIdea(site_id=site.id, keyword="single origin coffee uk", source="gsc",
                        impressions=2130, clicks=12, position=38.7),
            KeywordIdea(site_id=site.id, keyword="wholesale coffee south west", source="ai",
                        rationale="The page mentions supplying eleven cafes, but nothing targets the search."),
            KeywordIdea(site_id=site.id, keyword="best filter coffee beans", source="serp"),
        ])

        for engine_name, present, position, detail in [
            ("google", True, 14, None),
            ("google_ai_overview", False, None, "Shown, but this site is not cited."),
            ("chatgpt", False, None, "Asked as a question, it names three other roasters."),
        ]:
            s.add(VisibilityCheck(site_id=site.id, keyword="speciality coffee bristol", engine=engine_name,
                                  present=present, position=position, detail=detail,
                                  checked_at=NOW - timedelta(hours=3)))

        s.add(VisibilityAdvice(
            site_id=site.id, keyword="speciality coffee bristol", target_page_url=f"{ORIGIN}/",
            based_on_checked_at=NOW - timedelta(hours=3),
            diagnosis=("The page reads as a shop front rather than an answer. The three pages above it all "
                       "open by saying what speciality coffee is and where in Bristol to get it; this one "
                       "opens with how it roasts."),
            actions=(
                '[{"title": "Answer the search in the first paragraph", '
                '"detail": "The AI Overview cited three pages that define speciality coffee in their opening '
                'lines. This page opens with roasting method, so nothing on it answers the question being asked.", '
                '"addresses": "both"}, '
                '{"title": "Name Bristol in the title and meta description", '
                '"detail": "Neither currently mentions the city, while all three pages that outrank it do.", '
                '"addresses": "google"}, '
                '{"title": "Publish the roast list as its own page", '
                '"detail": "Six single origins are described in one paragraph. The pages that rank give each '
                'coffee its own heading and tasting notes.", "addresses": "both"}]'
            ),
        ))

        if not s.exec(select(Product)).first():
            s.add_all([
                Product(key="credits_10", name="10 credits", price_cents=200, credits=10, sort_order=10),
                Product(key="credits_50", name="50 credits", price_cents=500, credits=50,
                        badge="Best value", sort_order=20),
                Product(key="credits_200", name="200 credits", price_cents=1500, credits=200, sort_order=30),
            ])
        s.commit()
        print(f"seeded: user={EMAIL} site={site.id} page={page.id}")


if __name__ == "__main__":
    main()

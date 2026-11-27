"""Build the static research index from journal headings and metadata."""
import argparse
from datetime import date, datetime
from html import escape
from html.parser import HTMLParser
from itertools import groupby
from pathlib import Path
from shutil import copytree

FEATURED_POST = "2026-11-27-trace-backtest"

CATEGORIES = {
    "backtest": "백테스트",
    "research": "연구 기록",
    "validation": "설계와 검증",
    "evaluation": "실험 설계",
}


class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.headings = []
        self.heading = None

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.heading = []
        if tag == "meta":
            attributes = dict(attrs)
            name = attributes.get("name")
            if name and name.startswith("fintos:"):
                if name in self.fields:
                    raise ValueError(f"duplicate metadata {name}")
                self.fields[name] = (attributes.get("content") or "").strip()


    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.heading is not None:
            self.headings.append(" ".join("".join(self.heading).split()))
            self.heading = None


def read_posts(source):
    posts = []
    for path in sorted((source / "journal").glob("*/index.html")):
        parser = ArticleMetadata()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
            fields = parser.fields
            if len(parser.headings) != 1 or not parser.headings[0]:
                raise ValueError("expected exactly one non-empty article h1")
            title = parser.headings[0]
            summary, category, stamp = (
                fields[f"fintos:{key}"] for key in ("summary", "category", "published")
            )
            published = datetime.fromisoformat(stamp)
            if not (title and summary and category in CATEGORIES and published.tzinfo and
                    date.fromisoformat(path.parent.name[:10]) == published.date()):
                raise ValueError("expected title, summary, supported category and zoned publication time matching the folder date")
        except (KeyError, ValueError) as error:
            raise ValueError(f"{path}: {error}") from error
        posts.append(dict(path=path.parent.name, title=title, summary=summary,
                          category=category, published=published, stamp=stamp))
    # Stable folder order also applies when several articles share a publication time.
    return sorted(posts, key=lambda post: post["published"], reverse=True)


def article(post, prefix, heading):
    published = post["published"]
    when = f"{published.year}년 {published.month}월 {published.day}일"
    category = post["category"]
    href = escape(prefix + post["path"] + "/", quote=True)
    return (
        f'          <article class="journal-entry" data-entry data-category="{category}" data-year="{published.year}">\n'
        f'            <p class="journal-meta"><span>{CATEGORIES[category]}</span>'
        f'<time datetime="{escape(post["stamp"], quote=True)}">{when}</time></p>\n'
        f'            <{heading}><a href="{href}">{escape(post["title"])}</a></{heading}>\n'
        f'            <p class="journal-summary">{escape(post["summary"])}</p>\n'
        '          </article>'
    )


def replace(template, marker, content):
    begin, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    if template.count(begin) != 1 or template.count(end) != 1:
        raise ValueError(f"expected one {marker} marker pair")
    start = template.index(begin) + len(begin)
    stop = template.index(end, start)
    return template[:start] + "\n" + content + "\n" + template[stop:]


def build(source, destination):
    posts = read_posts(source)
    if not posts:
        raise ValueError("No published posts found")
    home = (source / "index.html").read_text(encoding="utf-8")
    archive = (source / "journal/index.html").read_text(encoding="utf-8")
    featured = next((post for post in posts if post["path"] == FEATURED_POST), None)
    if featured is None:
        raise ValueError(f"Featured post not found: {FEATURED_POST}")
    home = replace(home, "featured-post", (
        f'        <h1 id="title"><a href="journal/{FEATURED_POST}/">{escape(featured["title"])}</a></h1>\n'
        f'        <p class="featured-summary">{escape(featured["summary"])}</p>\n'
        f'        <a class="featured-read" href="journal/{FEATURED_POST}/">대표 연구 읽기</a>'
    ))
    home = replace(home, "latest-posts", "\n".join(article(post, "journal/", "h3") for post in posts[:3]))
    editions = []
    for year, entries in groupby(posts, key=lambda post: post["published"].year):
        editions.append(f'      <section class="journal-year" data-group aria-labelledby="year-{year}">\n'
                        f'        <h2 id="year-{year}">{year}년</h2>\n'
                        + "\n".join(article(post, "", "h3") for post in entries)
                        + "\n      </section>")
    archive = replace(archive, "archive-posts", "\n".join(editions))
    categories = {post["category"] for post in posts}
    archive = replace(archive, "category-options", "\n".join(
        f'          <option value="{key}">{label}</option>' for key, label in CATEGORIES.items() if key in categories))
    archive = replace(archive, "year-options", "\n".join(
        f'          <option value="{year}">{year}년</option>'
        for year in sorted({post["published"].year for post in posts}, reverse=True)))
    copytree(source, destination)
    (destination / "index.html").write_text(home, encoding="utf-8")
    (destination / "journal/index.html").write_text(archive, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New output directory for the generated site")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "site"
    if args.destination.resolve().is_relative_to(source):
        parser.error("output must be outside the source site")
    build(source, args.destination)

import argparse
from cl.scraper import run_scraper

parser = argparse.ArgumentParser()
parser.add_argument("query", nargs="?", default="surfboard")
parser.add_argument("--category")
parser.add_argument("--url", dest="search_url")
parser.add_argument("--radius", type=int, default=100)
args = parser.parse_args()
print(run_scraper(query=args.query, category=args.category, search_url=args.search_url, radius=args.radius, max_results=None))

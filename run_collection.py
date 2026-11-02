"""
Collect Google Maps places for a city in config/parameters.py, saving CSVs under ./output.

    Put GOOGLE_MAPS_API_KEY in .env, then:
    .venv/bin/python run_collection.py --dry-run                                # hexagon count only, no API calls
    .venv/bin/python run_collection.py --keywords "restaurant" --max-hexagons 2  # small paid test
    .venv/bin/python run_collection.py                                          # full run
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from modules.pipeline.data_collection_pipeline import DataCollectionPipeline, current_date

# All fields ("*"), same as the pipeline's prd default: bills every call at the Text Search
# Enterprise + Atmosphere SKU, but returns rating, reviews, price, hours, payment and services.
FIELD_MASK = "*"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", default="Osaka", help="Key in SHP_CITIES (default: Osaka)")
    parser.add_argument("--dry-run", action="store_true", help="Generate hexagons and estimate calls, no API calls")
    parser.add_argument("--keywords", nargs="+", help="Override the keyword list from config")
    parser.add_argument("--max-hexagons", type=int, help="Only search the first N hexagons (for testing)")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("Set GOOGLE_MAPS_API_KEY in .env first")

    pipeline = DataCollectionPipeline(
        city_name=args.city,
        api_key=api_key or "dry-run",
        field_mask=FIELD_MASK,
        output_dir=args.output_dir,
    )
    if args.keywords:
        pipeline.text_query = args.keywords

    pipeline.collect_country_shp_files()
    hexagons = pipeline.generate_hexagons()
    if not hexagons:
        sys.exit("No hexagons generated; check 'city' and 'level' in config/parameters.py")
    if args.max_hexagons:
        pipeline.hexagons = set(sorted(hexagons)[: args.max_hexagons])

    n_hex, n_kw = len(pipeline.hexagons), len(pipeline.text_query)
    print(f"\n{n_hex} hexagons x {n_kw} keywords = {n_hex * n_kw} searches minimum")
    print("Each search uses 1-3 API calls (20 results per page), and dense hexagons that hit 60 results")
    print("are split into 7 smaller ones and searched again, so the real count is higher.")
    print(f"Keywords: {pipeline.text_query}")

    if args.dry_run:
        return

    pipeline.get_google_maps_data_extraction()
    pipeline.combine_all_raw_data()
    print(
        f"\nDone. Combined file: "
        f"{args.output_dir}/google-data-extraction/{current_date}/combined/data-extraction.csv"
    )


if __name__ == "__main__":
    main()

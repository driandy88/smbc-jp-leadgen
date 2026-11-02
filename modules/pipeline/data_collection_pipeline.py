import io
import logging
from datetime import datetime
from typing import Optional

import geopandas as gpd
import pandas as pd

from config.gcs import GOOGLE_DATA_EXTRACTION_FOLDER_NAME, SHAPE_FILES_FOLDER_NAME
from config.parameters import COUNTRY_KEYWORDS_QUERY, MAIN_KEYWORDS_QUERY, SHP_CITIES
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader
from modules.google_maps.api import GoogleMapsAPI
from modules.h3_hexagon.hexagon_operations import HexagonGenerator
from modules.local_storage.storage import LocalDownloader, LocalUploader

logger = logging.getLogger(__name__)

current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


class DataCollectionPipeline:
    def __init__(
        self,
        city_name: str = None,
        MAX_RESOLUTION: int = 15,
        env: str = "prd",
        api_key: Optional[str] = None,
        field_mask: Optional[str] = None,
        output_dir: Optional[str] = None,
    ):
        self.shape_files_folder = SHAPE_FILES_FOLDER_NAME
        self.shp_cities_config = SHP_CITIES
        self.max_resolution = MAX_RESOLUTION
        if not field_mask:
            field_mask = "*" if env == "prd" else "places.attributions,places.id,places.name,nextPageToken"

        if not city_name:
            raise ValueError("city_name must be provided.")

        if city_name not in self.shp_cities_config:
            raise KeyError(f"City '{city_name}' not found in SHP_CITIES configuration.")

        self.config = self.shp_cities_config[city_name]
        self.level = self.config.get("level")
        self.city_shp_name = self.config.get("city")
        if not self.level:
            raise ValueError(f"'level' not specified for city '{city_name}' in configuration.")

        self.city_name = city_name
        self.country_code = self.config.get("country_code")

        # output_dir writes everything to local disk instead of GCS
        self.output_dir = output_dir
        if output_dir:
            self.downloader = LocalDownloader(root_dir=output_dir)
            self.uploader = LocalUploader(root_dir=output_dir)
        else:
            self.downloader = GCSDownloader(env=env)
            self.uploader = GCSUploader(env=env)
        self.hexagon_generator = HexagonGenerator(city_name=self.city_shp_name, level=self.level)
        self.google_maps_api = GoogleMapsAPI(
            field_mask=field_mask,
            api_key=api_key,
            language_code=self.config.get("language_code"),
            region_code=self.config.get("region_code"),
        )

        self.text_query = MAIN_KEYWORDS_QUERY + COUNTRY_KEYWORDS_QUERY.get(self.country_code, {})

        self.gdf = None
        self.env = env

    def collect_country_shp_files(self) -> Optional[gpd.GeoDataFrame]:
        try:
            folder_type = self.config.get("folder_type")

            if not all([folder_type, self.level, self.country_code]):
                raise ValueError("Missing required configuration keys.")

            # Read from a local folder when configured, e.g. "local_shp_dir": "gadm41_JPN_shp"
            local_shp_dir = self.config.get("local_shp_dir")
            if local_shp_dir:
                local_path = f"{local_shp_dir}/{folder_type}_{self.country_code}_{self.level}.shp"
                self.gdf = gpd.read_file(local_path)
                if self.gdf.empty:
                    raise ValueError(f"GeoDataFrame for {self.city_name} is empty after reading {local_path}.")
                return self.gdf

            gcs_path = f"{self.shape_files_folder}/{folder_type}_{self.country_code}_shp/{folder_type}_{self.country_code}_{self.level}"

            country_shp_files = self.downloader.download_to_memory(gcs_path)
            if not country_shp_files:
                raise FileNotFoundError(f"No files found for {self.city_name} at GCS path: {gcs_path}")

            temp_files = self.downloader.save_to_temp_files(country_shp_files, country_code=self.city_name)
            if not temp_files:
                raise FileNotFoundError(f"Failed to save {self.city_name} shapefiles to temporary files.")

            self.gdf = gpd.read_file(temp_files)
            if self.gdf.empty:
                raise ValueError(f"GeoDataFrame for {self.city_name} is empty after reading shapefiles.")

            return self.gdf

        except IndexError:
            print(f"{self.city_name} is not found.")
        except Exception as e:
            raise RuntimeError(f"Error collecting country shapefiles for {self.city_name}: {e}")

    def generate_hexagons(self) -> set:
        """
        Generates hexagons for the specified city using the provided hexagon generator.

        Returns:
            set: A set of generated hexagons.

        Raises:
            RuntimeError: If hexagon generation fails.
        """
        try:
            # Ensure GeoDataFrame is loaded
            if self.gdf is None:
                gdf = self.collect_country_shp_files()
                if gdf is None or gdf.empty:
                    raise RuntimeError(f"GeoDataFrame for {self.city_name} could not be loaded or is empty.")
            else:
                gdf = self.gdf

            self.hexagons = self.hexagon_generator.generate_hexagons(gdf)
            if not self.hexagons:
                raise RuntimeError(f"No hexagons generated for {self.city_name} at level {self.level}.")

            print(f"Generated {len(self.hexagons):,} hexagons for {self.city_name}.")
            return self.hexagons

        except Exception as e:
            print(f"[generate_hexagons] Error generating hexagons for city '{self.city_name}': {e}")
            return set()

    def retrieve_google_maps_doors(self, hex_id, keyword, MAX_THRESHOLD=60) -> pd.DataFrame:
        """
        Retrieves Google Maps doors based on the provided text query.

        Args:
            text_query (str): The search query for Google Maps.

        Returns:
            pd.DataFrame: DataFrame containing the search results.
        """
        results_df = pd.DataFrame()
        print(f"Extracting doors {self.city_name} for hex_id: {hex_id} for text_query: {keyword}.")

        min_lat, min_lng, max_lat, max_lng = self.hexagon_generator.get_hex_bbox(hex_id)
        if not all([min_lat, min_lng, max_lat, max_lng]):
            logger.warning("Bounds for the city must be defined in the configuration.")

        next_page_token = None
        count = 0
        while True:
            results = (
                self.google_maps_api.text_search_api(
                    text_query=keyword,
                    min_lat=min_lat,
                    min_lng=min_lng,
                    max_lat=max_lat,
                    max_lng=max_lng,
                    nextPageToken=next_page_token,
                )
                if next_page_token
                else self.google_maps_api.text_search_api(
                    text_query=keyword, min_lat=min_lat, min_lng=min_lng, max_lat=max_lat, max_lng=max_lng
                )
            )

            places = results.get("places", [])
            if not isinstance(places, list):
                logger.warning("Unexpected response format: 'places' is not a list.")
                break

            for place in places:
                place["keyword"] = keyword
                place["hex_id"] = hex_id

            if places:
                results_df = pd.concat([results_df, pd.DataFrame(places)], ignore_index=True)

            next_page_token = results.get("nextPageToken")
            count += 1
            if not next_page_token or count >= 5:
                break

        if results_df.empty:
            logger.warning(f"No results found for the text search {keyword} and hex id {hex_id}.")

        print(f"{hex_id} returns", results_df.shape[0], "doors for keyword:", keyword)

        results_df.reset_index(drop=True, inplace=True)

        gcs_path = f"{GOOGLE_DATA_EXTRACTION_FOLDER_NAME}/{current_date}/raw/{self.city_name}/{hex_id}-{keyword}.csv"

        upload_result = self.uploader.upload_dataframe(df=results_df, gcs_path=gcs_path, file_format="csv")
        if upload_result.get("failed") != []:
            print(f"Failed to upload {gcs_path} to GCS: {upload_result.get('failed')}")
            if not self.output_dir:
                self.uploader = GCSUploader(env=self.env)
            upload_result = self.uploader.upload_dataframe(df=results_df, gcs_path=gcs_path, file_format="csv")

        if results_df.shape[0] >= MAX_THRESHOLD:
            if self.max_resolution is not None:
                if self.hexagon_generator.get_hexagon_resolution(hex_id=hex_id) <= self.max_resolution:
                    child_hexagons = self.hexagon_generator.get_hexagon_children(hex_id=hex_id)
                    print(
                        f"Extracting doors for hex_id: {hex_id} for text_query: {keyword} at resolution {self.hexagon_generator.get_hexagon_resolution(hex_id=hex_id)}."
                    )
                    for hex_id_child in child_hexagons:
                        self.retrieve_google_maps_doors(hex_id=hex_id_child, keyword=keyword)

    def get_google_maps_data_extraction(self) -> None:
        """
        Main method to run the data collection pipeline.
        """
        for keyword in self.text_query:
            for hex_id in self.hexagons:
                print(f"Retrieving Google Maps doors for keyword: {keyword}")
                self.retrieve_google_maps_doors(hex_id=hex_id, keyword=keyword)

    def combine_all_raw_data(self) -> pd.DataFrame:
        """
        Combines all raw data files into a single DataFrame.

        Returns:
            pd.DataFrame: Combined DataFrame of all raw data.
        """
        prefix = f"{GOOGLE_DATA_EXTRACTION_FOLDER_NAME}/{current_date}/"
        # latest_date = self.downloader.get_folder_list(prefix)[0]
        cities_df = pd.DataFrame()

        cities = self.downloader.get_folder_list(prefix + "raw/")
        files = [{f"{city.split('/')[-2]}": self.downloader.get_file_list(city)} for city in cities]

        for file in files:
            for city, city_files in file.items():
                file_bytes = self.downloader.download_csv_files(gcs_paths=city_files)
                for file in city_files:
                    try:
                        city_df = pd.read_csv(io.BytesIO(file_bytes[file]))
                    except pd.errors.EmptyDataError as e:
                        logger.info(f"Empty data for file {file}: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"Error reading file {file}: {e}")
                        continue
                    city_df["extractionCities"] = city
                    city_df["extractionCountryCode"] = SHP_CITIES.get(city, {}).get("country_code", "Unknown")
                    city_df["extractionDate"] = current_date
                    cities_df = pd.concat([cities_df, city_df], ignore_index=True)
                    print("total dataframe size: ", cities_df.shape[0])

        if not self.output_dir:
            self.uploader = GCSUploader(env=self.env)
        self.uploader.upload_dataframe(
            df=cities_df,
            gcs_path=f"{GOOGLE_DATA_EXTRACTION_FOLDER_NAME}/{current_date}/combined/data-extraction.csv",
            file_format="csv",
        )

import logging
from typing import Optional

import google.auth
import pandas as pd
import requests as r
from google.auth.transport import requests as google_requests

from config.bq import GCP_PROJECT_ID as PROJECT

logger = logging.getLogger(__name__)


def get_adc_access_token(scope: str = "https://www.googleapis.com/auth/cloud-platform") -> str:
    """
    Return a fresh OAuth 2.0 bearer token using the current
    Application-Default Credentials chain.
    """
    creds, _ = google.auth.default(scopes=[scope])
    if not creds.valid:
        creds.refresh(google_requests.Request())
    return creds.token


class GoogleMapsAPI:
    BASE_URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(
        self,
        field_mask: str = "places.attributions,places.id,places.name,nextPageToken",
        api_key: Optional[str] = None,
        language_code: Optional[str] = None,
        region_code: Optional[str] = None,
    ):
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-FieldMask": field_mask,
        }
        # An API key bills its own project; otherwise fall back to Application-Default Credentials
        if api_key:
            self.headers["X-Goog-Api-Key"] = api_key
        else:
            self.token = get_adc_access_token()
            self.headers["Authorization"] = f"Bearer {self.token}"
            self.headers["X-Goog-User-Project"] = PROJECT
        self.language_code = language_code
        self.region_code = region_code

    def text_search_api(
        self,
        text_query: str,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        page_size: int = 20,
        timeout: int = 10,
        nextPageToken: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Search for places using a text query and location restriction.

        Args:
            text_query (str): The search query.
            min_lat (float): Minimum latitude.
            min_lng (float): Minimum longitude.
            max_lat (float): Maximum latitude.
            max_lng (float): Maximum longitude.
            page_size (int): Number of results per page.
            timeout (int): Request timeout in seconds.

        Returns:
            pd.DataFrame: DataFrame containing the search results.
        """
        data = {
            "textQuery": text_query,
            "pageSize": page_size,
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": min_lat, "longitude": min_lng},
                    "high": {"latitude": max_lat, "longitude": max_lng},
                }
            },
        }

        if self.language_code:
            data["languageCode"] = self.language_code
        if self.region_code:
            data["regionCode"] = self.region_code

        if nextPageToken:
            data["pageToken"] = nextPageToken

        try:
            response = r.post(self.BASE_URL, json=data, headers=self.headers, timeout=timeout)
            results = response.json()
        except r.RequestException as e:
            logger.error(f"Request to Google Maps API failed: {e}")
            return pd.DataFrame()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return pd.DataFrame()

        error = results.get("error")
        if error:
            status = error.get("status")
            message = error.get("message", "No error message")
            # A bad key or disabled API fails every call, so stop instead of looping through all hexagons
            if status in ("PERMISSION_DENIED", "UNAUTHENTICATED"):
                raise PermissionError(f"Google Maps API rejected the request ({status}): {message}")
            logger.error(f"Google Maps API error ({status}): {message}")
            return pd.DataFrame()

        return results

"""Mirador Real Estate's public NYC availability feed.

Pan Am Equities links its public ``AVAILABILITIES`` navigation to Mirador's
properties page.  That page uses a public Luxury Presence GraphQL endpoint.
The feed returns active property records, but a record is accepted here only
when its exact listed street text contains an unambiguous apartment label.
Building descriptions, counts, and floor-plan language are never expanded.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape

from ..core import SourceAdapter, fetch
from .rockrose import _dob_crosswalk


class MiradorAdapter(SourceAdapter):
    name = "mirador"
    description = "Mirador Real Estate public NYC active-listing GraphQL feed"

    PROPERTIES_URL = "https://miradorrealestate.com/properties"
    API_URL = "https://miradorrealestate.com/api-gw/graphql"
    COMPANY_ID = "49047760-4df7-417d-811a-2180aae8fa62"
    PAGE_SIZE = 100
    STATUS_IDS = (
        "a0012964-4f51-4430-abf8-6547c5ab6441",
        "df04ccbe-4621-4140-a504-ee1a17430bb7",
        "5f528253-abb7-484e-95c3-330269ac1105",
        "88b4ace6-f39b-4b25-a051-8f6dba976833",
    )
    QUERY = """query Properties(
      $companyId:String,
      $statusIds:[String!],
      $leaseProperty:Boolean,
      $offset:Int,
      $limit:Int,
      $sort:String,
      $sortDir:SortDirectionEnum
    ) {
      properties(
        companyId:$companyId,
        statusIds:$statusIds,
        leaseProperty:$leaseProperty,
        offset:$offset,
        limit:$limit,
        sort:$sort,
        sortDir:$sortDir
      ) {
        id name status originalStatus { id name }
        salesPrice reducedPrice bedroomCount bathCount fullBathCount halfBathCount threeQuarterBathCount
        addressLine1 addressLine2 addressCity addressState addressCountry postalCode fullAddress
        description syncedAt officeName attributionContact seoTitle seoDescription slug
        fromMLS mlsId mlsAttribution leaseProperty leasePrice currency
        leaseTermFrequencyInterval leaseTermFrequencyCount leasePeriod
        livingSpaceSize livingSpaceUnits lotAreaSize lotAreaUnits tags latitude longitude
        soldDate timeZone
      }
      propertiesCount(
        companyId:$companyId,
        statusIds:$statusIds,
        leaseProperty:$leaseProperty
      ) { count }
    }"""

    @staticmethod
    def _text(value):
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())

    @classmethod
    def _address_and_unit(cls, value):
        """Split a listed NYC address into premise and explicit unit label.

        The source supplies the unit in ``addressLine1`` (for example,
        ``60 W 23rd Street 634``).  The optional post-suffix direction handles
        addresses such as ``270 Park Avenue S 8C`` without turning ``S`` into
        the unit label.
        """
        text = cls._text(value).strip().rstrip(",")
        suffix = (
            r"street|st|avenue|ave|road|rd|place|pl|drive|dr|boulevard|blvd|"
            r"lane|ln|way|court|ct|terrace|ter|parkway|pkwy|square|sq|row"
        )
        match = re.match(
            rf"^(?P<address>.+?\b(?:{suffix})(?:\s+[NSEW])?)\s+#?"
            r"(?P<unit>[A-Za-z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9][A-Za-z0-9-]*)?)$",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        address = cls._text(match.group("address")).strip()
        unit = cls._text(match.group("unit")).strip()
        if not address or not unit:
            return None, None
        return address, unit

    @staticmethod
    def _number(value, integer=False):
        if value is None or value == "":
            return None
        match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
        return int(number) if integer else number

    @classmethod
    def _is_nyc(cls, item):
        state = cls._text(item.get("addressState")).upper()
        city = cls._text(item.get("addressCity")).lower()
        return state == "NY" and city in {
            "new york", "new york city", "brooklyn", "queens", "bronx",
            "staten island",
        }

    @classmethod
    def _parse_rows(cls, rows, source_url=None, feed_url=None, retrieved_at=None,
                    query=None, variables=None):
        source_url = source_url or cls.PROPERTIES_URL
        feed_url = feed_url or cls.API_URL
        retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        variables = variables or {}
        parsed = []
        for item in rows or []:
            if not isinstance(item, dict) or not item.get("id") or not cls._is_nyc(item):
                continue
            listed_address = cls._text(item.get("addressLine1"))
            address, unit_number = cls._address_and_unit(listed_address)
            if not (address and unit_number):
                continue
            slug = cls._text(item.get("slug"))
            detail_url = f"{cls.PROPERTIES_URL.rstrip('/')}/{slug}" if slug else source_url
            price = item.get("leasePrice")
            if price is None:
                price = item.get("salesPrice")
            lease_terms = json.dumps([{
                "period": item.get("leasePeriod"),
                "frequency_interval": item.get("leaseTermFrequencyInterval"),
                "frequency_count": item.get("leaseTermFrequencyCount"),
                "price": price,
            }], sort_keys=True)
            raw = {
                "source": cls.name,
                "source_url": source_url,
                "detail_url": detail_url,
                "feed_url": feed_url,
                "retrieved_at": retrieved_at,
                "query": query or cls.QUERY,
                "variables": variables,
                "listed_address": listed_address,
                "parsed_address": address,
                "parsed_unit_number": unit_number,
                "api_record": item,
            }
            parsed.append({
                "source_id": f"mirador-{item['id']}",
                "building_name": None,
                "address": address,
                "unit_number": unit_number,
                "bedrooms": cls._number(item.get("bedroomCount"), integer=True),
                "bathrooms": cls._number(item.get("bathCount")),
                "price": cls._number(price, integer=True),
                "sqft": cls._number(item.get("livingSpaceSize"), integer=True),
                "available_date": None,
                "lease_terms": lease_terms,
                "amenities": None,
                "description": cls._text(item.get("description")) or None,
                "floor_plan_url": None,
                "image_urls": None,
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "neighborhood": None,
                "borough": None,
                "zipcode": cls._text(item.get("postalCode")) or None,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, default=str, sort_keys=True),
            })
        return parsed

    def _variables(self, offset):
        return {
            "companyId": self.COMPANY_ID,
            "statusIds": list(self.STATUS_IDS),
            "leaseProperty": True,
            "offset": offset,
            "limit": self.PAGE_SIZE,
            "sort": "salesPrice",
            "sortDir": "DESC",
        }

    def pull(self):
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        all_rows = []
        expected = None
        offset = 0
        while expected is None or offset < expected:
            variables = self._variables(offset)
            body = json.dumps({"query": self.QUERY, "variables": variables}).encode()
            payload = json.loads(fetch(
                self.API_URL,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                data=body,
                method="POST",
                timeout=45,
            ))
            if payload.get("errors"):
                raise RuntimeError(f"Mirador GraphQL errors: {payload['errors']}")
            data = payload.get("data") or {}
            rows = data.get("properties") or []
            expected = int((data.get("propertiesCount") or {}).get("count") or 0)
            all_rows.extend(rows)
            if not rows:
                break
            offset += len(rows)
            if len(rows) < self.PAGE_SIZE:
                break
        parsed = self._parse_rows(
            all_rows,
            self.PROPERTIES_URL,
            self.API_URL,
            retrieved_at,
            self.QUERY,
            self._variables(0),
        )
        addresses = sorted({row["address"] for row in parsed})
        with ThreadPoolExecutor(max_workers=8) as executor:
            crosswalks = dict(zip(
                addresses,
                executor.map(
                    lambda address: _dob_crosswalk(address, retrieved_at), addresses
                ),
            ))
        for row in parsed:
            bbl, bbl_evidence = crosswalks[row["address"]]
            raw = json.loads(row["raw_json"])
            raw["bbl"] = bbl
            raw["bbl_evidence"] = bbl_evidence
            row["raw_json"] = json.dumps(raw, default=str, sort_keys=True)
        crosswalk_count = sum(1 for bbl, _ in crosswalks.values() if bbl)
        print(f"  {len(all_rows)} active API records; {len(parsed)} explicit NYC unit rows")
        print(f"  {crosswalk_count}/{len(addresses)} premises have a unique DOB NOW BBL crosswalk")
        return parsed

#!/usr/bin/env python3
import argparse
import datetime
import logging

import pydantic
import requests

log = logging.getLogger(__name__)

API_BASE = 'https://api.corona-zahlen.org'


class Delta(pydantic.BaseModel):
    cases: int
    deaths: int
    recovered: int


class Data(pydantic.BaseModel):
    ags: str
    name: str
    county: str
    population: int
    cases: int
    deaths: int
    casesPerWeek: int
    deathsPerWeek: int
    recovered: int
    weekIncidence: float
    casesPer100k: float
    delta: Delta


class Meta(pydantic.BaseModel):
    source: str
    contact: str
    info: str
    lastUpdate: datetime.datetime
    lastCheckedForUpdate: datetime.datetime


class District(pydantic.BaseModel):
    data: Data
    meta: Meta


# {
#   "data": {
#     "02000": {
#       "ags": "02000",
#       "name": "Hamburg",
#       "county": "SK Hamburg",
#       "population": 1847253,
#       "cases": 37535,
#       "deaths": 661,
#       "casesPerWeek": 2027,
#       "deathsPerWeek": 2,
#       "recovered": 27864,
#       "weekIncidence": 109.73050253538634,
#       "casesPer100k": 2031.9360693960166,
#       "delta": {
#         "cases": 0,
#         "deaths": 0,
#         "recovered": 350
#       }
#     }
#   },
#   "meta": {
#     "source": "Robert Koch-Institut",
#     "contact": "Marlon Lueckert (m.lueckert@me.com)",
#     "info": "https://github.com/marlon360/rki-covid-api",
#     "lastUpdate": "2021-01-04T00:00:00.000Z",
#     "lastCheckedForUpdate": "2021-01-04T13:59:49.832Z"
#   }
# }


def get_data(ags: str) -> District:
    response = requests.get(f'{API_BASE}/districts/{ags}')
    json = response.json()
    data = Data(**json["data"][ags])
    meta = Meta(**json["meta"])
    return District(data=data, meta=meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--loglevel', default='WARNING', help="Loglevel", action='store'
    )
    parser.add_argument('ags', help='Allgemeiner Gemeinde Schlüssel')
    # Get it by searching through the big endpoint /districts
    # curl 'https://api.corona-zahlen.org/districts' | jq '.data[] | select(.name == "Mein Kreis")'
    args = parser.parse_args()
    loglevel = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(loglevel, int):
        raise ValueError('Invalid log level: {}'.format(args.loglevel))
    logging.basicConfig(level=loglevel)

    data = get_data(args.ags)
    print(data)


if __name__ == '__main__':
    main()

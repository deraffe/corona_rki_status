#!/usr/bin/env python3
import argparse
import datetime
import functools
import logging
import os
import pathlib
import pickle

import pydantic
import requests
import sparkline

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


class HistoryItemIncidence(pydantic.BaseModel):
    weekIncidence: float
    date: datetime.datetime


class HistoryIncidenceData(pydantic.BaseModel):
    ags: str
    name: str
    history: list[HistoryItemIncidence]


class HistoryIncidence(pydantic.BaseModel):
    data: HistoryIncidenceData
    meta: Meta


def cache(*cargs):
    valid_for, get_timestamp = cargs

    def set_cache(fn):

        cache_file = pathlib.Path(
            os.environb.get(
                b'CORONA_STATUS_CACHE',
                pathlib.Path(__file__).parent.resolve() / 'corona_status.cache'
            )
        )

        @functools.wraps(fn)
        def cache_wrapper(*args, **kwargs):
            with cache_file.open('r+b') as cachef:
                try:  # FIXME check if cache_file has contents
                    cache = pickle.load(cachef)
                    cachef.seek(0)
                except (FileNotFoundError, EOFError):
                    cache = {}
                cache_key = (fn.__name__, args, tuple(kwargs))
                current_timestamp = datetime.datetime.now(datetime.timezone.utc)
                cache_timestamp, result = cache.get(cache_key, (None, None))
                log.debug(f"{current_timestamp=} {cache_timestamp=}")
                if cache_timestamp is None or (
                    current_timestamp - cache_timestamp
                ) >= valid_for:
                    log.debug(
                        f"cache_timestamp invalid or too old: {cache_timestamp}"
                    )
                    result = fn(*args, **kwargs)
                    data_timestamp = get_timestamp(result)
                    log.debug(
                        f"Saving result to cache with timestamp {data_timestamp}"
                    )
                    cache[cache_key] = (data_timestamp, result)
                else:
                    log.debug(f"Using cached data from {cache_timestamp}")
                pickle.dump(cache, cachef)
                return result

        return cache_wrapper

    return set_cache


def api_get(query: str) -> requests.Response:
    response = requests.get(f'{API_BASE}{query}')
    json = response.json()
    if not response.status_code == requests.codes.ok:
        raise RuntimeError(json)
    if 'error' in json:
        raise RuntimeError(json['error'].get('message'), json)
    return response


@cache(datetime.timedelta(hours=6), lambda d: d.meta.lastCheckedForUpdate)
def get_district(ags: str) -> District:
    response = api_get(f'/districts/{ags}')
    json = response.json()
    data = Data(**json["data"][ags])
    meta = Meta(**json["meta"])
    return District(data=data, meta=meta)


@cache(datetime.timedelta(hours=6), lambda d: d.meta.lastCheckedForUpdate)
def get_district_history(ags: str, days: int = 7) -> HistoryIncidence:
    response = api_get(f'/districts/{ags}/history/incidence/{days}')
    json = response.json()
    data = HistoryIncidenceData(**json["data"][ags])
    meta = Meta(**json["meta"])
    return HistoryIncidence(data=data, meta=meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--loglevel', default='WARNING', help="Loglevel", action='store'
    )
    parser.add_argument('ags', help='Allgemeiner Gemeinde Schlüssel')
    # Get it by searching through the big endpoint /districts
    # curl 'https://api.corona-zahlen.org/districts' | jq '.data[] | select(.name == "Mein Kreis")'
    parser.add_argument(
        '--days', help='How many days to go back', type=int, default=7
    )
    parser.add_argument(
        '--cache-file',
        type=pathlib.Path,
        help="Cache file"
    )
    args = parser.parse_args()
    loglevel = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(loglevel, int):
        raise ValueError('Invalid log level: {}'.format(args.loglevel))
    logging.basicConfig(level=loglevel)

    district = get_district(args.ags)
    history = get_district_history(args.ags, args.days)
    history_item_format = '{hi.date:%d}:{hi.weekIncidence:04.1f}'
    history_strings = []
    incidences = []
    for hi in history.data.history:
        history_strings.append(history_item_format.format(hi=hi))
        incidences.append(hi.weekIncidence)
    incidences.append(district.data.weekIncidence)
    sparklinestr = sparkline.sparkify(incidences)
    history_string = ''
    for i, histr in enumerate(history_strings):
        history_string += f'{histr}{sparklinestr[i]} '
    print(
        f'{district.data.name}: {history_string}{district.meta.lastUpdate:%d}:{district.data.weekIncidence:04.1f}{sparklinestr[-1]}'
    )


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import argparse
import datetime
import functools
import logging
import os
import pathlib
import pickle
from typing import Callable, Iterable, Optional

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
    valid_for: datetime.datetime
    get_timestamp: Callable
    catch_exceptions: Optional[Iterable[Exception]]
    if len(cargs) == 2:
        valid_for, get_timestamp = cargs
        catch_exceptions = None
    elif len(cargs) == 3:
        valid_for, get_timestamp, catch_exceptions = cargs
    else:
        raise ValueError(
            'cache(valid_for: datetime.datetime, get_timestamp: Callable, catch_exceptions: Optional[Iterable[Exception]] = None)'
        )

    def set_cache(fn):

        cache_file = pathlib.Path(
            os.environb.get(
                b'CORONA_STATUS_CACHE',
                pathlib.Path(__file__).parent.resolve() / 'corona_status.cache'
            )
        )

        @functools.wraps(fn)
        def cache_wrapper(*args, **kwargs):
            nonlocal valid_for, get_timestamp, catch_exceptions
            with cache_file.open('r+b') as cachef:
                try:
                    cache_storage = pickle.load(cachef)
                    cachef.seek(0)
                except (FileNotFoundError, EOFError):
                    cache_storage = {}
                cache_key = (fn.__name__, args, tuple(kwargs))
                current_timestamp = datetime.datetime.now(
                    datetime.timezone.utc
                )
                cache_timestamp, result = cache_storage.get(
                    cache_key, (None, None)
                )
                log.debug(f"{current_timestamp=} {cache_timestamp=}")
                if cache_timestamp is None or (
                    current_timestamp - cache_timestamp
                ) >= valid_for:
                    log.debug(
                        f"cache_timestamp invalid or too old: {cache_timestamp}"
                    )
                    if catch_exceptions is None:
                        catch_exceptions = tuple()
                    try:
                        result = fn(*args, **kwargs)
                    except catch_exceptions as e:
                        log.warn(
                            f'Caught exception (re-using cached result): {e}'
                        )
                        if cache_timestamp is None:
                            raise ValueError(
                                "Caught exception, but couldn't find cached value"
                            ) from e
                        data_timestamp = cache_timestamp
                    else:
                        data_timestamp = get_timestamp(result)
                    log.debug(
                        f"Saving result to cache with timestamp {data_timestamp}"
                    )
                    cache_storage[cache_key] = (data_timestamp, result)
                else:
                    log.debug(f"Using cached data from {cache_timestamp}")
                pickle.dump(cache_storage, cachef)
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


@cache(
    datetime.timedelta(hours=6), lambda d: d.meta.lastCheckedForUpdate,
    (RuntimeError, )
)
def get_district(ags: str) -> District:
    response = api_get(f'/districts/{ags}')
    json = response.json()
    data = Data(**json["data"][ags])
    meta = Meta(**json["meta"])
    return District(data=data, meta=meta)


@cache(
    datetime.timedelta(hours=6), lambda d: d.meta.lastCheckedForUpdate,
    (RuntimeError, )
)
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
        '--days', help='How many days to go back', type=int, default=14
    )
    parser.add_argument(
        '--full-days',
        help='How many days to show with values',
        type=int,
        default=6
    )
    parser.add_argument('--cache-file', type=pathlib.Path, help="Cache file")
    args = parser.parse_args()
    loglevel = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(loglevel, int):
        raise ValueError('Invalid log level: {}'.format(args.loglevel))
    logging.basicConfig(level=loglevel)

    non_full_days = args.days - args.full_days
    district = get_district(args.ags)
    history = get_district_history(args.ags, args.days)
    history_item_format = '{hi.date:%d}:{hi.weekIncidence:04.1f}'
    history_strings = []
    incidences = []
    for hi in history.data.history:
        history_strings.append(history_item_format.format(hi=hi))
        incidences.append(hi.weekIncidence)
    history_strings = history_strings[non_full_days:]
    incidences.append(district.data.weekIncidence)
    sparklinestr = sparkline.sparkify(incidences)
    history_string = ' '.join(history_strings)
    print(
        f'{district.data.name}: {sparklinestr} {history_string} {district.meta.lastUpdate:%d}:{district.data.weekIncidence:04.1f}'
    )


if __name__ == '__main__':
    main()

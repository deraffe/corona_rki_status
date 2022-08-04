#!/usr/bin/env python3
import argparse
import datetime
import functools
import logging
import os
import pathlib
import pickle
from typing import Any, Callable, Iterable, Optional, TypeVar, Union, cast

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


class HistoryItemCases(pydantic.BaseModel):
    cases: int
    date: datetime.datetime


class HistoryCasesData(pydantic.BaseModel):
    ags: str
    name: str
    history: list[HistoryItemCases]


class HistoryCases(pydantic.BaseModel):
    data: HistoryCasesData
    meta: Meta


History = Union[HistoryIncidence, HistoryCases]
F = TypeVar('F', bound=Callable)

def cache(*cargs) -> Callable[[F], F]:
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

    def set_cache(fn: F) -> F:

        cache_file = pathlib.Path(
            os.environb.get(
                b'CORONA_STATUS_CACHE',
                pathlib.Path(__file__).parent.resolve() / 'corona_status.cache'
            )
        )

        @functools.wraps(fn)
        def cache_wrapper(*args, **kwargs):
            nonlocal valid_for, get_timestamp, catch_exceptions
            if not cache_file.exists():
                cache_file.touch()
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

        return cast(F, cache_wrapper)

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
def get_district_history_incidence(
    ags: str, days: int = 7
) -> HistoryIncidence:
    response = api_get(f'/districts/{ags}/history/incidence/{days}')
    json = response.json()
    data = HistoryIncidenceData(**json["data"][ags])
    meta = Meta(**json["meta"])
    return HistoryIncidence(data=data, meta=meta)


@cache(
    datetime.timedelta(hours=6), lambda d: d.meta.lastCheckedForUpdate,
    (RuntimeError, )
)
def get_district_history_cases(
    ags: str, days: int = 7
) -> HistoryCases:
    response = api_get(f'/districts/{ags}/history/cases/{days}')
    json = response.json()
    data = HistoryCasesData(**json["data"][ags])
    meta = Meta(**json["meta"])
    return HistoryCases(data=data, meta=meta)

def get_district_history(ags: str, days: int = 7, attribute: str = 'incidence') -> History:
    match attribute:
        case 'incidence':
            return get_district_history_incidence(ags, days)
        case 'cases':
            return get_district_history_cases(ags, days)
        case _:
            raise NotImplementedError(f'Unkown attribute {attribute}')

def cmd_print(args):
    non_full_days = args.days - args.full_days
    district = get_district(args.ags)
    history = get_district_history_incidence(args.ags, args.days)

    history_item_format = '{hi.date:%d}:{hi.weekIncidence:04.1f}'
    history_strings = []
    incidences = []
    for hi in history.data.history:
        history_strings.append(history_item_format.format(hi=hi))
        incidences.append(hi.weekIncidence)
    history_strings = history_strings[non_full_days:]
    sparklinestr = sparkline.sparkify(incidences)
    history_string = ' '.join(history_strings)
    cases_per_incidence_level = district.data.population / 100000
    print(
        f'{district.data.name}({cases_per_incidence_level:.2f}): {sparklinestr} {history_string}'
    )


def cmd_draw(args):
    try:
        import sys

        import drawille
    except ImportError:
        log.error(
            'Please install the extra dependencies under "graph" to use this feature.'
        )
        sys.exit(1)

    history = get_district_history_incidence(args.ags, args.days).data.history

    def scale(
        target_min: float | int,
        target_max: float | int,
        value_min: float | int,
        value_max: float | int,
        value: float | int,
        flip=False
    ) -> float:
        value_in_scale = value - value_min
        percentage = value_in_scale / (value_max - value_min)
        if flip:
            percentage = 1 - percentage
        value_in_target_scale = percentage * (target_max - target_min)
        scaled_value = value_in_target_scale + target_min
        return scaled_value

    width, height = drawille.getTerminalSize()

    first_day = None
    max_seconds = 0
    get_seconds = lambda td: td.total_seconds()
    for index, day in enumerate(history):
        if index == 0:
            first_day = day.date
        max_seconds = max(max_seconds, get_seconds(day.date - first_day))

    def scale_day(value: int) -> float:
        return scale(0, width, 0, max_seconds, value)

    min_incidence = 700000
    max_incidence = 0
    for day in history:
        max_incidence = max(max_incidence, day.weekIncidence)
        min_incidence = min(min_incidence, day.weekIncidence)

    def scale_incidence(value: float, flip=False) -> float:
        return scale(0, height, min_incidence, max_incidence, value, flip=flip)

    c = drawille.Canvas()
    prev_x = None
    prev_y = None
    for day in history:
        x = scale_day(get_seconds(day.date - first_day))
        y = scale_incidence(day.weekIncidence, flip=True)
        if prev_x == None:
            c.set(x, y)
        else:
            for line_x, line_y in drawille.line(prev_x, prev_y, x, y):
                c.set(line_x, line_y)
        prev_x = x
        prev_y = y
    print(c.frame())


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
        default=7
    )
    parser.add_argument('--cache-file', type=pathlib.Path, help="Cache file")
    parser.add_argument(
        '--draw',
        action='store_true',
        help='Draw incidence instead of using sparklines'
    )
    args = parser.parse_args()
    loglevel = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(loglevel, int):
        raise ValueError('Invalid log level: {}'.format(args.loglevel))
    logging.basicConfig(level=loglevel)

    if args.draw:
        cmd_draw(args)
    else:
        cmd_print(args)


if __name__ == '__main__':
    main()

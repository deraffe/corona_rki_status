#!/usr/bin/env python3
import argparse
import dataclasses
import logging

log = logging.getLogger(__name__)

class Data:
    def __init__(self, ags: str, data: dict):
        self._ags = ags
        self.data = data["data"][ags]
        self.meta = data["meta"]

    @property
    def ags(self):
        assert self.data["ags"] == self._ags
        return self._ags

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


def get_data(ags: str) -> Data:
    #


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


if __name__ == '__main__':
    main()

import rapidfuzz
import unidecode


def normalize_search_text(value: str) -> str:
    return rapidfuzz.utils.default_process(unidecode.unidecode(value))


def find_matches(query: str, choices):
    return rapidfuzz.process.extract(
        query,
        choices,
        scorer=rapidfuzz.fuzz.WRatio,
        processor=normalize_search_text,
        limit=12,
    )

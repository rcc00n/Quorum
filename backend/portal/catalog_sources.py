"""Read-only registry validation and exact preview identity binding."""
from datetime import date
from urllib.parse import urlsplit

from .snapshot_validation import public_url

FIELDS = (
    'id', 'name', 'domain', 'allsides', 'mbfc', 'adfontes', 'audience',
    'kind', 'flank', 'tier', 'independence_group', 'rating_provenance',
    'rating_labels', 'ratings_checked_at', 'audience_source_url', 'audience_as_of',
)


def validate_sources(sources):
    ids = set()
    for source in sources:
        if source['id'] in ids:
            raise ValueError('duplicate_catalog_source')
        ids.add(source['id'])
        for field in ('rating_provenance', 'rating_labels'):
            if field not in source:
                continue
            value = source[field]
            if not isinstance(value, dict) or set(value) != {'allsides', 'mbfc', 'adfontes'}:
                raise ValueError('invalid_catalog_provenance')
            for item in value.values():
                if item is not None and (
                    not isinstance(item, str)
                    or len(item) > 2000
                    or field == 'rating_provenance' and not public_url(item)
                ):
                    raise ValueError('invalid_catalog_provenance')
        if source.get('audience_source_url') is not None and not public_url(source['audience_source_url']):
            raise ValueError('unsafe_catalog_url')
        for field in ('ratings_checked_at', 'audience_as_of'):
            if source.get(field) is not None and date.fromisoformat(source[field]).isoformat() != source[field]:
                raise ValueError('invalid_catalog_date')
        if (
            source.get('kind') not in (None, 'outlet', 'agency', 'official', 'military')
            or source.get('tier') not in (None, 'major', 'minor')
            or source.get('flank') not in (None, 'left', 'right', 'center')
        ):
            raise ValueError('invalid_catalog_cohort')


def host(url):
    name = (urlsplit(url).hostname or '').lower()
    return name[4:] if name.startswith('www.') else name


def bind_sources(payload, sources):
    # DECISION(2026-10-24, rcc00n/Codex): explicit evidence source_id wins; otherwise
    # exact normalized hostname only. Conflicts fail; never infer identities from outlet names.
    registry = {source['id']: source for source in sources}
    domains = {}
    for source in sources:
        domains.setdefault(host('https://' + source['domain']), []).append(source)
    urls = {}
    for story in payload['stories']:
        for claim in story['claims']:
            for evidence in claim['evidence']:
                if evidence.get('source_id'):
                    identities = urls.setdefault(evidence['url'], set())
                    identities.add(evidence['source_id'])
                    if len(identities) > 1:
                        raise ValueError('ambiguous_reasoning_source')

    def resolve(value):
        explicit = urls.get(value['url'], set())
        if len(explicit) > 1:
            raise ValueError('ambiguous_reasoning_source')
        if explicit:
            return registry.get(next(iter(explicit)))
        matches = domains.get(host(value['url']), [])
        if len(matches) > 1:
            raise ValueError('ambiguous_catalog_domain')
        return matches[0] if matches else None

    return resolve

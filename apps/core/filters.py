import operator
from functools import reduce

from django.db import models
from rest_framework.filters import SearchFilter

from apps.core.normalizers import normalize_parcel_code


class NormalizedSearchFilter(SearchFilter):
    """
    SearchFilter compatible con codigos de parcela canonicos.

    Permite que busquedas como A-01, A01 o A 01 encuentren registros guardados
    como A-1, sin cambiar la representacion visible del dato.
    """

    def get_search_terms(self, request):
        raw_value = request.query_params.get(self.search_param, '')
        if normalize_parcel_code(raw_value):
            return [raw_value]
        return super().get_search_terms(request)

    def _term_alternatives(self, term):
        values = [term]
        normalized_code = normalize_parcel_code(term)
        if normalized_code:
            values.append(normalized_code)

        deduped = []
        seen = set()
        for value in values:
            key = str(value).casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        return deduped

    def filter_queryset(self, request, queryset, view):
        search_fields = self.get_search_fields(view, request)
        search_terms = self.get_search_terms(request)

        if not search_fields or not search_terms:
            return queryset

        orm_lookups = [self.construct_search(str(search_field), queryset) for search_field in search_fields]

        base = queryset
        conditions = []
        for term in search_terms:
            term_queries = []
            for alternative in self._term_alternatives(term):
                term_queries.extend(models.Q(**{orm_lookup: alternative}) for orm_lookup in orm_lookups)
            conditions.append(reduce(operator.or_, term_queries))

        queryset = queryset.filter(reduce(operator.and_, conditions))

        if self.must_call_distinct(queryset, search_fields):
            queryset = queryset.filter(pk=models.OuterRef('pk'))
            queryset = base.filter(models.Exists(queryset))
        return queryset

"""Simple pass10 doctring."""

from graphene_django.settings import graphene_settings
from graphql import get_default_backend

backend = get_default_backend()
schema = graphene_settings.SCHEMA


def get_gql_data(request, query, variable_values={}):
    """Function run GraphQL Query to get schema mapping information."""
    document = backend.document_from_string(schema, query)
    gql_result = document.execute(context_value=request, variable_values=variable_values)
    return gql_result.data

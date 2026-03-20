"""QLever HTTP API client for executing SPARQL queries and managing the server."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union


class QLeverError(Exception):
    """Error from the QLever server."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class QLeverClient:
    """Client for the QLever SPARQL engine HTTP API.

    Example usage:
        client = QLeverClient("http://localhost:7001")
        result = client.query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
        rows = client.query_df("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
    """

    JSON_ACTIONS = {'qlever_json_export', 'sparql_json_export'}

    def __init__(self, endpoint: str, max_send: int = 5000,
                 timeout: float = 300.0):
        self.endpoint = endpoint.rstrip('/')
        self.max_send = max_send
        self.timeout = timeout

    def query(self, sparql: str, action: str = "qlever_json_export",
              max_send: Optional[int] = None) -> Union[Dict[str, Any], str]:
        """Execute a SPARQL query and return the result.

        For JSON actions (qlever_json_export, sparql_json_export) returns a dict.
        For text actions (tsv_export, csv_export, turtle_export) returns a string.
        """
        params = {
            'query': sparql,
            'send': max_send if max_send is not None else self.max_send,
            'action': action,
        }
        url = self.endpoint + '/?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url)

        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                pass
            raise QLeverError(
                f"HTTP {e.code}: {body}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise QLeverError(f"Connection error: {e.reason}") from e

        if action in self.JSON_ACTIONS:
            return json.load(response)
        else:
            return response.read().decode('utf-8')

    def query_df(self, sparql: str) -> List[Dict[str, str]]:
        """Execute a query and return results as a list of dicts.

        Each dict represents a row with variable names as keys.
        """
        result = self.query(sparql, action='sparql_json_export')
        bindings = result.get('results', {}).get('bindings', [])
        rows = []
        for binding in bindings:
            row = {}
            for var, info in binding.items():
                row[var] = info.get('value', '')
            rows.append(row)
        return rows

    def stats(self) -> Dict[str, Any]:
        """Get server statistics (index name, triple counts, etc.)."""
        return self._get_json({'cmd': 'stats'})

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._get_json({'cmd': 'cache-stats'})

    def clear_cache(self, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Clear the query cache. Requires access token if configured."""
        params: Dict[str, str] = {'cmd': 'clear-cache'}
        if access_token:
            params['access-token'] = access_token
        return self._get_json(params)

    def _get_json(self, params: Dict[str, str]) -> Dict[str, Any]:
        """Make a GET request and return parsed JSON."""
        url = self.endpoint + '/?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url)

        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                pass
            raise QLeverError(
                f"HTTP {e.code}: {body}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise QLeverError(f"Connection error: {e.reason}") from e

        return json.load(response)

    def __repr__(self) -> str:
        return f'QLeverClient({self.endpoint!r})'

"""Async QLever HTTP API client with batch/parallel query capabilities."""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator, Dict, List, Optional, Union


class AsyncQLeverError(Exception):
    """Error from the QLever server (async client)."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AsyncQLeverClient:
    """Async client for the QLever SPARQL engine HTTP API.

    Uses asyncio with a ThreadPoolExecutor to wrap synchronous urllib calls,
    requiring no external dependencies beyond the Python standard library.

    Example usage::

        import asyncio
        from utils.async_client import AsyncQLeverClient

        async def main():
            async with AsyncQLeverClient("http://localhost:7001") as client:
                result = await client.query("SELECT * WHERE { ?s ?p ?o } LIMIT 10")

                results = await client.batch_query([
                    "SELECT * WHERE { ?s ?p ?o } LIMIT 5",
                    "SELECT * WHERE { ?s a ?type } LIMIT 5",
                ])

                async for row in client.stream_query("SELECT * WHERE { ?s ?p ?o }"):
                    print(row)

                async for page in client.paginate("SELECT * WHERE { ?s ?p ?o }"):
                    print(f"Got page with {len(page)} rows")

        asyncio.run(main())
    """

    JSON_ACTIONS = {'qlever_json_export', 'sparql_json_export'}

    def __init__(
        self,
        endpoint: str,
        max_send: int = 5000,
        timeout: float = 300.0,
        max_workers: int = 8,
    ):
        """Create a new AsyncQLeverClient.

        Args:
            endpoint: Base URL of the QLever server (e.g. "http://localhost:7001").
            max_send: Default maximum number of result rows to send back.
            timeout: HTTP request timeout in seconds.
            max_workers: Thread pool size for concurrent urllib calls.
        """
        self.endpoint = endpoint.rstrip('/')
        self.max_send = max_send
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AsyncQLeverClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Shut down the internal thread pool executor."""
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Core async query
    # ------------------------------------------------------------------

    async def query(
        self,
        sparql: str,
        action: str = "qlever_json_export",
        max_send: Optional[int] = None,
    ) -> Union[Dict[str, Any], str]:
        """Execute a SPARQL query asynchronously and return the result.

        For JSON actions (qlever_json_export, sparql_json_export) returns a dict.
        For text actions (tsv_export, csv_export, turtle_export) returns a string.

        Args:
            sparql: The SPARQL query string.
            action: QLever export action to use.
            max_send: Maximum rows to return (overrides instance default).

        Returns:
            Parsed JSON dict for JSON actions, raw string for text actions.

        Raises:
            AsyncQLeverError: On HTTP or connection errors.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_query,
            sparql,
            action,
            max_send,
        )

    async def batch_query(
        self,
        queries: List[str],
        action: str = "qlever_json_export",
        max_send: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple SPARQL queries in parallel.

        All queries are dispatched concurrently via asyncio.gather and resolved
        when every query has completed (or any one raises an exception).

        Args:
            queries: List of SPARQL query strings.
            action: QLever export action to use for every query.
            max_send: Maximum rows per query (overrides instance default).

        Returns:
            List of results in the same order as the input queries.

        Raises:
            AsyncQLeverError: If any individual query fails.
        """
        tasks = [
            self.query(sparql, action=action, max_send=max_send)
            for sparql in queries
        ]
        results: List[Dict[str, Any]] = await asyncio.gather(*tasks)
        return results

    async def stream_query(
        self,
        sparql: str,
        action: str = "sparql_json_export",
        max_send: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, str], None]:
        """Execute a SPARQL query and yield result rows one at a time.

        The full result set is fetched in one HTTP call (QLever does not support
        true HTTP streaming for SPARQL).  Rows are then yielded one by one so
        callers can process them incrementally without loading the entire list
        into memory at once.

        Args:
            sparql: The SPARQL query string.
            action: Must be a JSON action so that bindings can be parsed.
            max_send: Maximum rows to fetch (overrides instance default).

        Yields:
            One dict per result row with variable names as keys and string values.

        Raises:
            AsyncQLeverError: On HTTP or connection errors.
        """
        result = await self.query(sparql, action=action, max_send=max_send)
        bindings = result.get('results', {}).get('bindings', [])
        for binding in bindings:
            row: Dict[str, str] = {
                var: info.get('value', '')
                for var, info in binding.items()
            }
            yield row

    async def paginate(
        self,
        sparql: str,
        page_size: int = 1000,
        action: str = "sparql_json_export",
    ) -> AsyncGenerator[List[Dict[str, str]], None]:
        """Auto-paginate a SPARQL query using LIMIT/OFFSET, yielding pages.

        The method appends ``LIMIT <page_size> OFFSET <offset>`` to the
        supplied *sparql* string and advances the offset until an empty page
        is returned.

        Note: The caller's query should NOT include a LIMIT or OFFSET clause,
        as this method appends its own.

        Args:
            sparql: The SPARQL query string (without LIMIT/OFFSET).
            page_size: Number of rows per page.
            action: Must be a JSON action so that bindings can be parsed.

        Yields:
            Each page as a list of row dicts (empty list signals end of data).

        Raises:
            AsyncQLeverError: On HTTP or connection errors.
        """
        offset = 0
        while True:
            paginated = f"{sparql.rstrip()} LIMIT {page_size} OFFSET {offset}"
            result = await self.query(paginated, action=action,
                                      max_send=page_size)
            bindings = result.get('results', {}).get('bindings', [])
            page: List[Dict[str, str]] = [
                {var: info.get('value', '') for var, info in binding.items()}
                for binding in bindings
            ]
            yield page
            if len(page) < page_size:
                # Last (possibly partial) page — no more data.
                break
            offset += page_size

    # ------------------------------------------------------------------
    # Async admin helpers
    # ------------------------------------------------------------------

    async def stats(self) -> Dict[str, Any]:
        """Get server statistics asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_json, {'cmd': 'stats'}
        )

    async def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_json, {'cmd': 'cache-stats'}
        )

    async def clear_cache(
        self, access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clear the query cache asynchronously."""
        params: Dict[str, str] = {'cmd': 'clear-cache'}
        if access_token:
            params['access-token'] = access_token
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_json, params
        )

    # ------------------------------------------------------------------
    # Synchronous helpers (run inside the thread pool)
    # ------------------------------------------------------------------

    def _sync_query(
        self,
        sparql: str,
        action: str,
        max_send: Optional[int],
    ) -> Union[Dict[str, Any], str]:
        """Synchronous query implementation — called from the executor."""
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
            raise AsyncQLeverError(
                f"HTTP {e.code}: {body}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise AsyncQLeverError(f"Connection error: {e.reason}") from e

        if action in self.JSON_ACTIONS:
            return json.load(response)
        return response.read().decode('utf-8')

    def _sync_get_json(self, params: Dict[str, str]) -> Dict[str, Any]:
        """Synchronous GET + JSON parse — called from the executor."""
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
            raise AsyncQLeverError(
                f"HTTP {e.code}: {body}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise AsyncQLeverError(f"Connection error: {e.reason}") from e

        return json.load(response)

    def __repr__(self) -> str:
        return f'AsyncQLeverClient({self.endpoint!r})'

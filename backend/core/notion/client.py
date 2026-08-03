from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from backend.config.settings import settings
from loguru import logger
import asyncio

_MAX_RETRIES = 3
_RETRY_DELAYS = (0.5, 1.0)
_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429}


def _is_retryable_error(error: Exception) -> bool:
    status = getattr(error, "status", None) or getattr(error, "status_code", None)
    if status is not None:
        try:
            return int(status) in _RETRYABLE_HTTP_STATUS or int(status) >= 500
        except (TypeError, ValueError):
            pass
    return isinstance(error, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError))

class NotionClient:
    _instance = None

    def __init__(self):
        self.client = AsyncClient(auth=settings.notion.token, notion_version="2022-06-28")
        logger.info("Notion Client initialized")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = NotionClient()
        return cls._instance

    async def close(self):
        await self.client.aclose()

    async def _call_with_retry(self, operation, label: str):
        for attempt in range(_MAX_RETRIES):
            try:
                return await operation()
            except Exception as exc:
                if attempt == _MAX_RETRIES - 1 or not _is_retryable_error(exc):
                    raise
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    f"Notion {label} temporairement indisponible "
                    f"(tentative {attempt + 1}/{_MAX_RETRIES}) : {exc}; retry dans {delay}s"
                )
                await asyncio.sleep(delay)

    async def query_database(self, database_id: str, filter_params: dict = None, sorts: list = None, page_size: int = None):
        """
        Query a database while handling pagination automatically.
        """
        results = []
        has_more = True
        next_cursor = None

        try:
            while has_more:
                # Workaround for missing databases.query in notion-client
                request_body = {}
                if filter_params:
                    request_body["filter"] = filter_params
                if sorts:
                    request_body["sorts"] = sorts
                if page_size:
                    request_body["page_size"] = page_size
                if next_cursor:
                    request_body["start_cursor"] = next_cursor

                response = await self._call_with_retry(
                    lambda: self.client.request(
                        path=f"databases/{database_id}/query",
                        method="POST",
                        body=request_body,
                    ),
                    "query_database",
                )
                results.extend(response.get("results", []))
                
                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")
                
            logger.info(f"Retrieved {len(results)} items from database {database_id}")
            return results

        except APIResponseError as e:
            logger.error(f"Notion API Error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error querying Notion: {e}")
            raise

    async def retrieve_database(self, database_id: str) -> dict:
        """Retrieve a database schema (properties, title, etc.)."""
        try:
            return await self._call_with_retry(
                lambda: self.client.databases.retrieve(database_id=database_id),
                "retrieve_database",
            )
        except Exception as e:
            logger.error(f"Error retrieving database {database_id}: {e}")
            raise

    async def update_page(self, page_id: str, properties: dict):
        """Update a page properties."""
        try:
            return await self._call_with_retry(
                lambda: self.client.pages.update(page_id=page_id, properties=properties),
                "update_page",
            )
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {e}")
            raise

    async def create_page(self, parent_db_id: str, properties: dict, children: list = None):
        """Create a new page in a database."""
        try:
            kwargs = {
                "parent": {"database_id": parent_db_id},
                "properties": properties
            }
            if children:
                kwargs["children"] = children
                
            return await self._call_with_retry(
                lambda: self.client.pages.create(**kwargs),
                "create_page",
            )
        except Exception as e:
            logger.error(f"Error creating page in db {parent_db_id}: {e}")
            raise

    async def archive_page(self, page_id: str):
        """Archive (soft-delete) a page."""
        try:
            return await self._call_with_retry(
                lambda: self.client.pages.update(page_id=page_id, archived=True),
                "archive_page",
            )
        except Exception as e:
            logger.error(f"Error archiving page {page_id}: {e}")
            raise

    async def update_block(self, block_id: str, **kwargs):
        """Update a block's content (e.g. to_do checked state)."""
        try:
            return await self._call_with_retry(
                lambda: self.client.blocks.update(block_id=block_id, **kwargs),
                "update_block",
            )
        except Exception as e:
            logger.error(f"Error updating block {block_id}: {e}")
            raise

    async def append_block_children(self, block_id: str, children: list):
        """Append children blocks to a block (or page)."""
        try:
            return await self._call_with_retry(
                lambda: self.client.blocks.children.append(block_id=block_id, children=children),
                "append_block_children",
            )
        except Exception as e:
            logger.error(f"Error appending children to block {block_id}: {e}")
            raise

    async def retrieve_block_children(self, block_id: str) -> dict:
        """Retrieve ALL children blocks with automatic pagination."""
        all_blocks: list = []
        has_more = True
        next_cursor = None
        try:
            while has_more:
                kwargs: dict = {"block_id": block_id, "page_size": 100}
                if next_cursor:
                    kwargs["start_cursor"] = next_cursor
                response = await self._call_with_retry(
                    lambda: self.client.blocks.children.list(**kwargs),
                    "retrieve_block_children",
                )
                all_blocks.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")
            return {"results": all_blocks, "has_more": False}
        except Exception as e:
            logger.error(f"Error retrieving children of block {block_id}: {e}")
            raise

notion_client = NotionClient.get_instance()

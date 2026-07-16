from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from backend.config.settings import settings
from loguru import logger
import asyncio

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

                response = await self.client.request(
                    path=f"databases/{database_id}/query",
                    method="POST",
                    body=request_body
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
            return await self.client.databases.retrieve(database_id=database_id)
        except Exception as e:
            logger.error(f"Error retrieving database {database_id}: {e}")
            raise

    async def update_page(self, page_id: str, properties: dict):
        """Update a page properties."""
        try:
            return await self.client.pages.update(page_id=page_id, properties=properties)
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
                
            return await self.client.pages.create(**kwargs)
        except Exception as e:
            logger.error(f"Error creating page in db {parent_db_id}: {e}")
            raise

    async def archive_page(self, page_id: str):
        """Archive (soft-delete) a page."""
        try:
            return await self.client.pages.update(page_id=page_id, archived=True)
        except Exception as e:
            logger.error(f"Error archiving page {page_id}: {e}")
            raise

    async def update_block(self, block_id: str, **kwargs):
        """Update a block's content (e.g. to_do checked state)."""
        try:
            return await self.client.blocks.update(block_id=block_id, **kwargs)
        except Exception as e:
            logger.error(f"Error updating block {block_id}: {e}")
            raise

    async def append_block_children(self, block_id: str, children: list):
        """Append children blocks to a block (or page)."""
        try:
            return await self.client.blocks.children.append(block_id=block_id, children=children)
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
                response = await self.client.blocks.children.list(**kwargs)
                all_blocks.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")
            return {"results": all_blocks, "has_more": False}
        except Exception as e:
            logger.error(f"Error retrieving children of block {block_id}: {e}")
            raise

notion_client = NotionClient.get_instance()
